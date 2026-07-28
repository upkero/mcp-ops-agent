import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from src.app.api.v1.dependencies import OrchestratorDep
from src.app.api.v1.dependencies.security import require_api_key
from src.app.contracts.agent.agent_event import AgentEvent
from src.app.core.sse import format_sse
from src.app.exceptions.base import BaseAppException
from src.app.schemas.invoke import InvokeRequest

logger = logging.getLogger(__name__)

# No feature noun in the path: the host and port already say which service this
# is, and what gets invoked is the agent — which decides for itself how many
# tools to call — not one named MCP tool.
router = APIRouter(tags=["agent"])


@router.post("/invoke", dependencies=[Depends(require_api_key)])
async def invoke(body: InvokeRequest, orchestrator: OrchestratorDep) -> StreamingResponse:
    """Run the agent for one instruction and stream its steps as Server-Sent Events.

    Thin transport: it only forwards the message and relays the orchestrator's
    event stream (tool_call → tool_result → … → final). It knows nothing about the
    tools themselves — those live behind the MCP server the orchestrator calls.
    """

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in orchestrator.run(body.message):
                yield format_sse(event)
        except BaseAppException as exc:
            # The 200 + SSE headers have already been sent, so a failure is
            # delivered as a terminal error EVENT, not an HTTP error status.
            yield format_sse(
                AgentEvent(type="error", data={"error_code": exc.error_code, "detail": exc.detail})
            )
        except Exception:
            logger.exception("agent stream failed")
            yield format_sse(
                AgentEvent(
                    type="error",
                    data={"error_code": "internal_error", "detail": "Agent run failed."},
                )
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
