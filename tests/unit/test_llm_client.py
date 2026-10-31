"""`complete()` against a fake SDK: what goes on the wire, what comes back, and what a failure looks like.

The replies are real `ChatCompletion` models, so a field the SDK renames breaks these tests
rather than production.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import APIConnectionError
from openai.types.chat import ChatCompletion
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.app.contracts.llm.llm_message import LLMMessage
from src.app.contracts.llm.tool_call import ToolCall
from src.app.core.settings.llm import LLMSettings
from src.app.exceptions.llm import LLMGenerationError, LLMInputError
from src.app.llm.openai_compatible_llm_client import OpenAICompatibleLLMClient

_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_customer",
        "description": "Look up customers.",
        "parameters": {"type": "object", "properties": {"name_or_id": {"type": "string"}}},
    },
}
_USER = [LLMMessage(role="system", content="be brief"), LLMMessage(role="user", content="hi")]


def _completion(message: dict[str, Any], *, usage: dict[str, Any] | None = None, **extra: Any) -> ChatCompletion:
    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 1,
            "model": "stub-model-2026",
            "choices": [{"index": 0, "finish_reason": extra.pop("finish_reason", "stop"), "message": message}],
            "usage": usage,
            **extra,
        }
    )


def _client(
    reply: ChatCompletion | Exception, base_url: str = "http://localhost:11434/v1", **settings: Any
) -> tuple[OpenAICompatibleLLMClient, AsyncMock]:
    sdk = MagicMock()
    sdk.chat.completions.create = (
        AsyncMock(side_effect=reply) if isinstance(reply, Exception) else AsyncMock(return_value=reply)
    )
    llm_settings = LLMSettings(provider="ollama", model="stub-model", base_url=base_url, **settings)
    return OpenAICompatibleLLMClient(settings=llm_settings, client=sdk), sdk.chat.completions.create


def _sent(create: AsyncMock) -> dict[str, Any]:
    (call,) = create.await_args_list
    return dict(call.kwargs)


async def test_empty_messages_are_rejected_before_any_request() -> None:
    client, create = _client(_completion({"role": "assistant", "content": "x"}))

    with pytest.raises(LLMInputError):
        await client.complete([])

    create.assert_not_awaited()


async def test_a_text_reply_becomes_the_response_with_its_usage() -> None:
    client, create = _client(
        _completion(
            {"role": "assistant", "content": "Hello."},
            usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
        )
    )

    response = await client.complete(_USER)

    assert response.content == "Hello."
    assert response.model == "stub-model-2026"
    assert response.finish_reason == "stop"
    assert response.usage == {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
    assert response.tool_calls == ()
    sent = _sent(create)
    assert sent["model"] == "stub-model"
    assert sent["messages"] == [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}]
    assert sent["temperature"] == 0.0
    assert sent["max_tokens"] == 1024
    # Not OpenRouter, and no tools: neither the cost flag nor a tool list is sent.
    assert not {"tools", "tool_choice", "extra_body", "reasoning_effort"} & sent.keys()


async def test_a_tool_call_reply_is_parsed_and_the_tools_go_out_with_auto_choice() -> None:
    client, create = _client(
        _completion(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "lookup_customer", "arguments": '{"name_or_id": "Anna"}'},
                    }
                ],
            },
            finish_reason="tool_calls",
        )
    )

    response = await client.complete(_USER, tools=[_TOOL])

    assert response.content == ""
    assert response.tool_calls == (ToolCall("call_1", "lookup_customer", '{"name_or_id": "Anna"}'),)
    sent = _sent(create)
    assert sent["tools"] == [_TOOL]
    assert sent["tool_choice"] == "auto"


async def test_the_assistant_tool_turn_and_its_result_are_sent_in_the_provider_shape() -> None:
    client, create = _client(_completion({"role": "assistant", "content": "Found her."}))
    call = ToolCall("call_1", "lookup_customer", '{"name_or_id": "Anna"}')

    await client.complete(
        [
            *_USER,
            LLMMessage(role="assistant", content="", tool_calls=(call,)),
            LLMMessage(role="tool", content='{"count": 1}', tool_call_id="call_1"),
        ]
    )

    assert _sent(create)["messages"][2:] == [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "lookup_customer", "arguments": '{"name_or_id": "Anna"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": '{"count": 1}'},
    ]


async def test_openrouter_is_asked_for_the_cost_and_the_cost_is_recorded(
    spans: InMemorySpanExporter, metric_value: Callable[..., float]
) -> None:
    client, create = _client(
        _completion(
            {"role": "assistant", "content": "ok"},
            usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12, "cost": 0.25},
        ),
        base_url="https://openrouter.ai/api/v1",
        temperature=None,
        max_tokens=None,
        reasoning_effort="low",
    )
    before = metric_value("llm.cost", provider="openrouter")

    await client.complete(_USER)

    sent = _sent(create)
    assert sent["extra_body"] == {"usage": {"include": True}}
    assert sent["reasoning_effort"] == "low"
    assert "temperature" not in sent and "max_tokens" not in sent
    (span,) = spans.get_finished_spans()
    attributes = dict(span.attributes or {})
    assert attributes["gen_ai.provider.name"] == "openrouter"
    assert attributes["llm.cost"] == 0.25
    assert metric_value("llm.cost", provider="openrouter") == before + 0.25


async def test_the_span_says_what_the_reply_was_and_never_what_it_said(spans: InMemorySpanExporter) -> None:
    client, _ = _client(
        _completion(
            {"role": "assistant", "content": "a secret answer"},
            usage={"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12},
            finish_reason="length",
        )
    )

    await client.complete(_USER)

    (span,) = spans.get_finished_spans()
    attributes = dict(span.attributes or {})
    assert span.name == "chat stub-model"
    assert attributes["gen_ai.response.id"] == "chatcmpl-1"
    assert attributes["gen_ai.response.model"] == "stub-model-2026"
    assert attributes["gen_ai.response.finish_reasons"] == ("length",)
    assert attributes["gen_ai.usage.input_tokens"] == 7
    assert attributes["gen_ai.usage.output_tokens"] == 5
    assert attributes["server.address"] == "localhost"
    assert "a secret answer" not in str(attributes)


async def test_a_provider_error_is_typed_and_names_its_cause_on_span_and_metric(
    spans: InMemorySpanExporter, metric_value: Callable[..., float]
) -> None:
    cause = APIConnectionError(request=httpx.Request("POST", "http://localhost:11434/v1/chat/completions"))
    client, _ = _client(cause)
    before = metric_value("gen_ai.client.operation.duration", **{"error.type": "APIConnectionError"})

    with pytest.raises(LLMGenerationError) as raised:
        await client.complete(_USER)

    assert raised.value.__cause__ is cause
    (span,) = spans.get_finished_spans()
    assert (span.attributes or {})["error.type"] == "APIConnectionError"
    assert metric_value("gen_ai.client.operation.duration", **{"error.type": "APIConnectionError"}) == before + 1


@pytest.mark.parametrize(
    "reply",
    [
        _completion({"role": "assistant", "content": ""}),
        ChatCompletion.model_validate(
            {"id": "c", "object": "chat.completion", "created": 1, "model": "m", "choices": []}
        ),
    ],
    ids=["empty-content-no-tools", "no-choices"],
)
async def test_an_empty_reply_is_a_generation_error(reply: ChatCompletion, spans: InMemorySpanExporter) -> None:
    client, _ = _client(reply)

    with pytest.raises(LLMGenerationError):
        await client.complete(_USER)

    (span,) = spans.get_finished_spans()
    assert (span.attributes or {})["error.type"] == "LLMGenerationError"
