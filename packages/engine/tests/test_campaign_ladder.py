"""The difficulty proof of the 19-level campaign (spec 0051)."""

import itertools
import json
from pathlib import Path

import pytest

from shield_engine.game import BoardValidationError, get_level, get_levels
from shield_engine.game.calibration import (
    GENERIC_ONE_NODE_BOTS,
    LAZY_BOT_EXCEPTIONS,
    check_reports,
    lazy_bots,
    lazy_value,
    reference,
    run_plan,
)

TIERS = ("Easy", "Medium", "Hard")


async def _outcome(level_id: str, plan) -> tuple[bool, float]:  # type: ignore[no-untyped-def]
    """(cleared, lazy value); a board the level rejects never clears."""
    try:
        result = await run_plan(level_id, plan)
    except BoardValidationError:
        return False, 0.0
    return result.score.won and result.stop is None, lazy_value(result.score)


@pytest.mark.spec("ENG-LADDER-004")
async def test_lazy_bots_do_not_clear_a_level_except_the_allowed_ones() -> None:
    assert {
        "easy-1": {"briefing_memoriser", "campaign_regex"},
        "easy-4": {"briefing_ml"},
    } == LAZY_BOT_EXCEPTIONS
    for level in get_levels():
        bots = lazy_bots(level.id)
        assert set(bots) == {
            "block_all",
            "allow_all",
            "briefing_memoriser",
            "campaign_regex",
            "briefing_ml",
        }
        for name, plan in bots.items():
            cleared, _ = await _outcome(level.id, plan)
            allowed = name in LAZY_BOT_EXCEPTIONS.get(level.id, set())
            assert cleared is False or allowed, (level.id, name)


@pytest.mark.spec("ENG-LADDER-005")
async def test_each_reference_board_clears_and_needs_its_new_idea() -> None:
    for level in get_levels():
        ref = reference(level.id)
        cleared, _ = await _outcome(level.id, ref.board)
        assert cleared, level.id
        without, _ = await _outcome(level.id, ref.without_idea)
        assert not without, level.id


@pytest.mark.spec("ENG-LADDER-006")
async def test_the_best_lazy_value_never_rises_by_more_than_five_points_in_a_tier() -> None:
    best: dict[str, float] = {}
    for level in get_levels():
        values = []
        # Every lazy bot counts here, also one that a level is allowed to lose to.
        for plan in lazy_bots(level.id).values():
            values.append((await _outcome(level.id, plan))[1])
        best[level.id] = max(values)
    for tier in TIERS:
        ids = [lv.id for lv in get_levels() if lv.difficulty == tier]
        for earlier, later in itertools.pairwise(ids):
            assert best[later] <= best[earlier] + 0.05, (earlier, later, best)


@pytest.mark.spec("ENG-LADDER-007")
async def test_every_limit_binds_on_the_reference_board() -> None:
    for level in get_levels():
        ref = reference(level.id)
        limits = set()
        if level.constraints.max_check_nodes is not None:
            limits.add("nodes")
        if level.constraints.max_total_cost_usd is not None:
            limits.add("cost")
        if level.constraints.max_avg_latency_ms is not None:
            limits.add("latency")
        assert set(ref.limit_breakers) == limits, level.id
        for name, plan in ref.limit_breakers.items():
            cleared, _ = await _outcome(level.id, plan)
            assert not cleared, (level.id, name)


@pytest.mark.spec("ENG-LADDER-009")
async def test_a_dual_use_tool_switched_off_always_or_never_does_not_clear() -> None:
    dual = [lv for lv in get_levels() if lv.agent and any(t.dual_use for t in lv.agent.tools)]
    assert [lv.id for lv in dual] == [
        "medium-6",
        "medium-7",
        "hard-1",
        "hard-5",
        "hard-6",
        "hard-7",
    ]
    for level in dual:
        ref = reference(level.id)
        assert set(ref.dual_use) == {"always_off", "never_off"}, level.id
        for name, plan in ref.dual_use.items():
            cleared, _ = await _outcome(level.id, plan)
            assert not cleared, (level.id, name)


REPORT = Path(__file__).resolve().parents[1] / "calibration" / "report.json"


@pytest.mark.spec("ENG-LADDER-010")
def test_the_calibration_report_shows_no_generic_one_node_clear() -> None:
    assert set(GENERIC_ONE_NODE_BOTS) == {"jev_general", "safety_check_default", "prompt_guard"}
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    levels = {entry["level_id"]: entry for entry in report["levels"]}
    assert set(levels) == {lv.id for lv in get_levels()}
    for level_id, entry in levels.items():
        assert set(entry["one_node"]) == set(GENERIC_ONE_NODE_BOTS), level_id
        assert not any(run["cleared"] for run in entry["one_node"].values()), level_id


@pytest.mark.spec("DEV-LADDER-001")
def test_the_ci_check_names_each_level_without_a_passing_report(tmp_path: Path) -> None:
    def entry(level_id: str, **over: object) -> dict[str, object]:
        base: dict[str, object] = {
            "level_id": level_id,
            "version": get_level(level_id).version,
            "reference_clears": 5,
            "reference_runs": 5,
            # A live agent varies by about one prompt (~600 points); the limit is 700.
            "reference_stdev": 616.0,
            "lazy_clears": [],
            "one_node": {name: {"cleared": False} for name in GENERIC_ONE_NODE_BOTS},
        }
        base.update(over)
        return base

    good = [entry(lv.id) for lv in get_levels()]
    # One failed run of five is allowed, and the spread counts only the cleared runs.
    good[0] = entry(
        "easy-1",
        reference_clears=4,
        reference_scores=[10000, 10000, 10000, 4582, 9400],
        reference_stdev=2167.0,
    )
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"levels": good}), encoding="utf-8")
    assert check_reports(path) == []

    bad = list(good)
    bad[0] = entry("easy-1", reference_clears=3)
    bad[1] = entry("easy-2", reference_stdev=701.0)
    bad[2] = entry("easy-3", lazy_clears=["allow_all"])
    bad[3] = entry("easy-4", version=get_level("easy-4").version + 1)
    bad = [e for e in bad if e["level_id"] != "hard-7"]
    path.write_text(json.dumps({"levels": bad}), encoding="utf-8")
    assert sorted(check_reports(path)) == ["easy-1", "easy-2", "easy-3", "easy-4", "hard-7"]
