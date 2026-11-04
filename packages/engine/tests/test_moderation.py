import pytest

from shield_engine import LlamaGuardModerator
from shield_engine.testing import ScriptedChatModel


@pytest.mark.spec("ENG-MOD-001")
async def test_safe_answer_is_not_flagged() -> None:
    result = await LlamaGuardModerator(ScriptedChatModel(["safe"])).moderate("hello")

    assert not result.flagged
    assert result.categories == ()
    assert result.raw == "safe"


@pytest.mark.spec("ENG-MOD-002")
@pytest.mark.parametrize("raw", ["unsafe\nS1,S13", "unsafe\nS1\nS13", " unsafe \n S1, S13 "])
async def test_unsafe_answer_is_flagged_with_categories(raw: str) -> None:
    result = await LlamaGuardModerator(ScriptedChatModel([raw])).moderate("prompt")

    assert result.flagged
    assert result.categories == ("S1", "S13")


@pytest.mark.spec("ENG-MOD-003")
async def test_model_error_fails_open_by_default() -> None:
    model = ScriptedChatModel([RuntimeError("rate limited")])

    result = await LlamaGuardModerator(model).moderate("prompt")

    assert not result.flagged
    assert result.error == "rate limited"


@pytest.mark.spec("ENG-MOD-004")
async def test_model_error_fails_closed_when_configured() -> None:
    model = ScriptedChatModel([RuntimeError("timeout")])

    result = await LlamaGuardModerator(model, fail_closed=True).moderate("prompt")

    assert result.flagged
    assert result.categories == ("ERROR",)
    assert result.error == "timeout"
