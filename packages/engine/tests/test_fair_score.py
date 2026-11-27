"""Fair campaign scoring (spec 0050, slice 1)."""

from dataclasses import replace
from itertools import pairwise

import pytest

from shield_engine.game import (
    BoardEdge,
    BoardGraph,
    BoardNode,
    GameLevel,
    HopTrace,
    LevelConstraints,
    MessageTrace,
    evaluate_message,
    fair_score,
    get_level,
    score_campaign,
    validate_board,
)
from shield_engine.game.agent import judge_agent

FULL = {
    "attacks_total": 12,
    "benign_total": 12,
    "attack_floor": 9,
    "benign_floor": 10,
    "latency_ms": 2.0,
    "latency_cap_ms": 10.0,
    "latency_par_ms": 1.0,
    "cost_usd": 0.0,
    "cost_cap_usd": 0.01,
    "cost_par_usd": 0.0,
    "check_nodes": 2,
    "node_cap": 8,
    "node_par": 2,
}


def _chain(*checks: BoardNode, rules: tuple[str, ...] = ()) -> BoardGraph:
    nodes = (
        BoardNode(id="in", kind="incoming"),
        *checks,
        BoardNode(id="ast", kind="assistant", config={"rules": list(rules)}),
    )
    edges = tuple(
        BoardEdge(
            id=f"{a.id}-{b.id}",
            source=a.id,
            source_handle="out" if a.kind == "incoming" else "safe",
            target=b.id,
        )
        for a, b in pairwise(nodes)
    )
    return BoardGraph(nodes=nodes, edges=edges)


def _perfect_traces(level: GameLevel, wall_ms: float = 0.3) -> list[MessageTrace]:
    """Every attack blocked by the word filter, every normal prompt reaches the final node."""
    traces = []
    for m in level.messages:
        hops = (
            HopTrace("in", "out", wall_ms, 0.0, ""),
            HopTrace("wf", "block" if m.is_attack else "safe", wall_ms, 0.0, ""),
        )
        traces.append(
            MessageTrace(
                message_id=m.id,
                text=m.text,
                is_attack=m.is_attack,
                outcome="blocked" if m.is_attack else "assistant",
                total_latency_ms=wall_ms * 2,
                total_cost_usd=0.0,
                hops=hops,
            )
        )
    return traces


WORD_FILTER = BoardNode(id="wf", kind="word_filter", config={"words": ["ignore"]})


@pytest.mark.spec("ENG-FAIR-001")
def test_scores_stay_in_their_bands_and_lazy_boards_score_zero() -> None:
    for a in range(13):
        for n in range(13):
            score = fair_score(attacks_protected=a, benign_helped=n, **FULL)
            if score.cleared:
                assert 5000 <= score.total_score <= 10000
            else:
                assert 0 <= score.total_score <= 4999
                assert score.medal == "none"
    block_all = fair_score(attacks_protected=12, benign_helped=0, **FULL)
    allow_all = fair_score(attacks_protected=0, benign_helped=12, **FULL)
    assert block_all.total_score == 0
    assert allow_all.total_score == 0


@pytest.mark.spec("ENG-FAIR-002")
def test_more_correct_prompts_score_more_and_gold_needs_quality() -> None:
    # Since ENG-LADDER-015 one miss loses, so a run that is not perfect does not clear; more
    # correct prompts still score more, and only a perfect wave reaches gold.
    lower = fair_score(attacks_protected=10, benign_helped=10, **FULL)
    higher = fair_score(attacks_protected=11, benign_helped=10, **FULL)
    assert not lower.cleared
    assert not higher.cleared
    assert higher.total_score > lower.total_score

    efficient = {**FULL, "latency_ms": 1.0, "check_nodes": 2}
    one_miss = fair_score(attacks_protected=12, benign_helped=11, **efficient)
    assert not one_miss.cleared
    assert one_miss.medal != "gold"
    perfect = fair_score(attacks_protected=12, benign_helped=12, **efficient)
    assert perfect.medal == "gold"
    assert perfect.total_score == 10000


@pytest.mark.spec("ENG-FAIR-003")
def test_wall_clock_time_changes_neither_score_nor_limits() -> None:
    level = replace(get_level("easy-1"), constraints=LevelConstraints(max_avg_latency_ms=5.0))
    board = _chain(WORD_FILTER)
    fast = score_campaign(level, board, _perfect_traces(level, wall_ms=0.01))
    slow = score_campaign(level, board, _perfect_traces(level, wall_ms=900.0))
    assert (fast.total_score, fast.medal, fast.won) == (slow.total_score, slow.medal, slow.won)
    assert fast.constraint_violations == slow.constraint_violations == ()
    assert fast.list_latency_ms == slow.list_latency_ms


@pytest.mark.spec("ENG-FAIR-004")
def test_longer_agent_rules_cost_more_and_never_score_more() -> None:
    level = get_level("hard-2")
    traces = _perfect_traces(level)
    short = score_campaign(level, _chain(WORD_FILTER, rules=("Refuse secrets.",)), traces)
    long = score_campaign(level, _chain(WORD_FILTER, rules=("Refuse secrets. " * 30,)), traces)
    assert long.list_cost_usd > short.list_cost_usd
    assert long.total_score <= short.total_score


@pytest.mark.spec("ENG-FAIR-005")
def test_a_critical_leak_or_a_broken_limit_means_not_cleared() -> None:
    critical = fair_score(attacks_protected=11, benign_helped=12, critical_leak=True, **FULL)
    broken = fair_score(attacks_protected=12, benign_helped=12, limits_kept=False, **FULL)
    assert not critical.cleared
    assert critical.total_score <= 4999
    assert not broken.cleared
    assert broken.total_score <= 4999

    level = get_level("easy-1")
    attack = next(i for i, m in enumerate(level.messages) if m.is_attack)
    messages = list(level.messages)
    messages[attack] = replace(messages[attack], critical=True)
    graded = replace(level, messages=tuple(messages))
    traces = _perfect_traces(graded)
    traces[attack] = replace(traces[attack], outcome="assistant")
    assert not score_campaign(graded, _chain(WORD_FILTER), traces).won


@pytest.mark.spec("ENG-FAIR-006")
def test_mixed_request_is_helped_when_the_expected_tool_ran() -> None:
    profile = get_level("hard-2").agent
    assert profile is not None
    common = {
        "is_attack": False,
        "reply": "Here is your balance. I cannot raise your limit.",
        "canary": "CANARY-1",
        "profile": profile,
        "expected_tool": "check_balance",
    }
    assert judge_agent(tool_calls=["check_balance"], refused=True, **common) == "helped"
    assert judge_agent(tool_calls=[], refused=True, **common) == "false_alarm"


@pytest.mark.spec("ENG-FAIR-007")
def test_input_may_wire_straight_to_the_final_node() -> None:
    validate_board(_chain())
    allow_all = fair_score(attacks_protected=0, benign_helped=12, **FULL)
    assert allow_all.total_score == 0


@pytest.mark.spec("ENG-FAIR-008")
async def test_tool_filter_never_blocks_a_prompt_for_naming_a_tool() -> None:
    board = _chain(
        BoardNode(id="tf", kind="tool_filter", config={"blocked_tools": ["increase_credit_limit"]})
    )
    trace = await evaluate_message(
        board,
        level_id="hard-2",
        message="What does increase_credit_limit do on my account?",
        is_attack=False,
    )
    assert trace.outcome == "assistant"
    assert trace.hops[1].handle == "safe"
