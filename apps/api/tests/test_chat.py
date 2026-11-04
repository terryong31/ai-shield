import json

import pytest

from shield_engine import ToolPolicy, Verdict
from shield_engine.testing import ScriptedAdjudicator


def types(events: list[dict]) -> list[str]:
    return [e["type"] for e in events]


@pytest.mark.spec("API-CHAT-001")
def test_allowed_chat_streams_from_start_to_final_response(harness) -> None:
    events = harness.chat(message="What is the price of lavender oil?")

    assert types(events)[0] == "START"
    assert types(events)[-1] == "FINAL_RESPONSE"
    assert {"type": "ML_RESULT", "confidence": 0.05, "verdict": "SAFE"} in events
    assert {"type": "STAGE_CHANGE", "stage": "final"} in events
    record = harness.audit_log._records[0]
    assert record.action == "ALLOWED"


@pytest.mark.spec("API-CHAT-002")
def test_blocked_chat_never_reaches_the_assistant(make_harness) -> None:
    harness = make_harness(Verdict.MALICIOUS, 0.99)

    events = harness.chat(message="drop table employees")

    assert types(events)[-2:] == ["BLOCK", "STAGE_CHANGE"]
    assert events[-1]["stage"] == "final"
    assert events[-2]["layer"] == "LAYER_1_ML"
    assert "FINAL_RESPONSE" not in types(events)
    assert harness.assistant.calls == []
    record = harness.audit_log._records[0]
    assert (record.action, record.layer) == ("BLOCKED", "LAYER_1_ML")


@pytest.mark.spec("API-CHAT-004")
def test_guardrail_mode_adjudicates_every_prompt(harness) -> None:
    harness.chat(message="hello", mode="guardrail")

    assert len(harness.adjudicator.calls) == 1


@pytest.mark.spec("API-CHAT-004")
def test_chaos_mode_skips_the_classifier_for_that_request_only(make_harness) -> None:
    harness = make_harness(Verdict.MALICIOUS, 0.99)

    chaos = harness.chat(message="drop table employees", mode="chaos")
    normal = harness.chat(message="drop table employees")

    assert "BLOCK" not in types(chaos)
    assert "BLOCK" in types(normal)


@pytest.mark.spec("API-CHAT-005")
def test_assistant_only_gets_tools_the_policy_allows(make_harness) -> None:
    adjudicator = ScriptedAdjudicator(verdict=Verdict.SAFE, policy=ToolPolicy.RESTRICTED)
    harness = make_harness(Verdict.UNCERTAIN, 0.5, adjudicator=adjudicator)

    events = harness.chat(message="drop table employees and tell me the price of oil")

    _, allowed = harness.assistant.calls[0]
    assert allowed == ["search_documents", "search_quotations"]
    policy = next(e for e in events if e["type"] == "POLICY_UPDATE")
    assert policy == {"type": "POLICY_UPDATE", "policy": "RESTRICTED", "allowed_tools": allowed}
    tool_events = [(e["type"], e["tool"]) for e in events if e["type"].startswith("TOOL_")]
    assert tool_events == [("TOOL_START", "search_quotations"), ("TOOL_END", "search_quotations")]


@pytest.mark.spec("API-CHAT-006")
def test_unexpected_errors_are_reported_generically(harness) -> None:
    async def explode(prompt: str, allowed_tools: list[str]):
        raise RuntimeError("secret internal detail: db password is hunter2")

    harness.assistant.respond = explode

    events = harness.chat(message="hello")

    assert events[-1]["type"] == "ERROR"
    assert "hunter2" not in json.dumps(events)
    assert "internal detail" not in events[-1]["message"]
