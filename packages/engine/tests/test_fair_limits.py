"""Limits stop the run, and the board size caps (spec 0050)."""

import itertools
import json
from dataclasses import replace

import pytest

from shield_engine.game import (
    BoardEdge,
    BoardGraph,
    BoardNode,
    BoardValidationError,
    LevelConstraints,
    get_level,
    run_wave,
    validate_board_for_level,
)
from shield_engine.game import levels as levels_module
from shield_engine.ports import ChatCompletion, JevEvaluation
from shield_engine.testing import ScriptedJevClient, ScriptedUsageChatModel


def _chain(*checks: BoardNode) -> BoardGraph:
    nodes = (BoardNode(id="in", kind="incoming"), *checks, BoardNode(id="ast", kind="assistant"))
    edges = tuple(
        BoardEdge(
            id=f"{a.id}-{b.id}",
            source=a.id,
            source_handle="out" if a.kind in {"incoming", "text_cleanup"} else "safe",
            target=b.id,
        )
        for a, b in itertools.pairwise(nodes)
    )
    return BoardGraph(nodes=nodes, edges=edges)


def _with_constraints(
    monkeypatch: pytest.MonkeyPatch, level_id: str, constraints: LevelConstraints
) -> None:
    level = replace(get_level(level_id), constraints=constraints)
    original = levels_module.get_level

    def patched(lid: str):  # type: ignore[no-untyped-def]
        return level if lid == level_id else original(lid)

    # The runner and the scorer each hold their own name for get_level (spec 0055).
    from shield_engine.game import runner, scoring

    for module in (runner, scoring):
        if hasattr(module, "get_level"):
            monkeypatch.setattr(module, "get_level", patched)


@pytest.mark.spec("ENG-FAIR-009")
async def test_a_prompt_over_the_time_limit_stops_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_constraints(monkeypatch, "easy-1", LevelConstraints(max_avg_latency_ms=8.0))
    model = ScriptedUsageChatModel(
        replies=[],
        default=ChatCompletion(
            text=json.dumps({"flagged": False, "reason": "ok"}), input_tokens=10, output_tokens=5
        ),
    )
    board = _chain(BoardNode(id="sc", kind="safety_check"))

    result = await run_wave(board, level_id="easy-1", check_model=model, check_model_for=None)

    stop = result.stop
    assert stop is not None
    assert stop.reason == "time_limit"
    assert stop.prompt_index == 1
    assert stop.node_id == "sc"
    assert stop.limit == 8.0
    assert [(s.node_id, s.latency_ms) for s in stop.path] == [("sc", 85.0)]
    assert len(result.traces) == 1
    assert len(model.calls) == 1
    assert result.score.total_score == 0
    assert result.score.won is False


@pytest.mark.spec("ENG-FAIR-010")
async def test_a_wave_over_the_cost_budget_stops_at_that_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_constraints(monkeypatch, "easy-1", LevelConstraints(max_total_cost_usd=0.00012))
    jev = ScriptedJevClient(replies=[JevEvaluation(probability=0.05, input_tokens=40)] * 30)
    board = _chain(BoardNode(id="jv", kind="jev", config={"question": "Is this an attack?"}))

    result = await run_wave(board, level_id="easy-1", jev_client=jev)

    stop = result.stop
    assert stop is not None
    assert stop.reason == "budget"
    assert stop.prompt_index == 3
    assert stop.node_id == "jv"
    assert [(s.node_id, s.cost_usd) for s in stop.path] == [("jv", 0.00005)]
    assert len(result.traces) == 3
    assert len(jev.calls) == 3
    assert result.score.total_score == 0
    assert result.score.won is False


@pytest.mark.spec("ENG-FAIR-011")
def test_boards_over_the_node_caps_are_rejected() -> None:
    level = replace(get_level("hard-1"), constraints=LevelConstraints())
    nine = _chain(*(BoardNode(id=f"w{i}", kind="word_filter") for i in range(9)))
    with pytest.raises(BoardValidationError, match="at most 8 check nodes"):
        validate_board_for_level(nine, level)

    three_models = _chain(
        BoardNode(id="j1", kind="jev"),
        BoardNode(id="j2", kind="jev"),
        BoardNode(id="lr", kind="llm_review"),
    )
    with pytest.raises(BoardValidationError, match="at most 2 model nodes"):
        validate_board_for_level(three_models, level)

    validate_board_for_level(
        _chain(BoardNode(id="j1", kind="jev"), BoardNode(id="lr", kind="llm_review")), level
    )
