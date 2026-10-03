from datetime import datetime, timedelta, timezone

import pytest

from src.app.prompts import Prompt, get_prompt
from src.app.services.orchestrator import _today_label


def test_the_agent_system_prompt_is_loaded_from_disk() -> None:
    prompt = get_prompt("ops_agent.system")
    assert prompt.name == "ops_agent.system"
    assert "never invent" in prompt.text


def test_the_prompt_id_changes_with_the_wording() -> None:
    """The whole point of the digest: a reworded prompt is a different id."""
    assert Prompt("p", "one").id != Prompt("p", "two").id


def test_an_unknown_prompt_names_what_is_available() -> None:
    with pytest.raises(KeyError, match="ops_agent.system"):
        get_prompt("no-such-prompt")


def test_render_refuses_to_guess_at_a_missing_placeholder() -> None:
    prompt = Prompt("p", "Reply in {reply_language} about {topic}.")
    assert prompt.placeholders == {"reply_language", "topic"}

    with pytest.raises(KeyError, match="topic"):
        prompt.render(reply_language="English")

    assert prompt.render(reply_language="English", topic="slots") == "Reply in English about slots."


def test_the_system_prompt_gives_the_weekday_and_zone_of_today() -> None:
    # 2026-10-03 was a Saturday; "next Monday" is only computable if the prompt says so.
    now = datetime(2026, 10, 3, 9, 0, tzinfo=timezone(timedelta(hours=3), "MSK"))

    rendered = get_prompt("ops_agent.system").render(today=_today_label(now))

    assert "Today is Saturday 2026-10-03 (MSK)." in rendered


def test_the_system_prompt_forbids_claiming_bookings_the_agent_cannot_make() -> None:
    text = " ".join(get_prompt("ops_agent.system").text.split())  # ignore line wrapping

    assert "cannot create, change or cancel bookings" in text
    assert "Never state or imply that an action happened unless a tool call" in text
    assert "must never say that a booking" in text
