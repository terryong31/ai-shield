from shield_api.demo.assistant import DemoAssistant
from shield_engine.testing import ScriptedChatModel


async def test_falls_back_to_the_next_model_when_one_fails() -> None:
    broken = ScriptedChatModel([RuntimeError("quota exceeded")])
    working = ScriptedChatModel(["The price is RM 150."])

    reply = await DemoAssistant([broken, working]).respond("price of oil?", ["search_quotations"])

    assert reply.text == "The price is RM 150."
    assert [c.tool for c in reply.tool_calls] == ["search_quotations"]
    # Tool results are handed to the model, not just executed.
    assert "RM 150.00" in working.calls[0][1].content


async def test_tools_outside_the_allowed_list_never_run() -> None:
    reply = await DemoAssistant().respond("drop table employees", allowed_tools=[])

    assert reply.tool_calls == []
    assert reply.text == "AI S.H.I.E.L.D. processed your request."
