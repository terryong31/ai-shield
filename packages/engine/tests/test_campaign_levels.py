from __future__ import annotations

import json

import pytest

import shield_engine.game as game_mod
from shield_engine.game import (
    BoardEdge,
    BoardGraph,
    BoardNode,
    BoardValidationError,
    get_level,
    get_levels,
    run_wave,
)
from shield_engine.game.calibration import chain
from shield_engine.ports import ChatCompletion
from shield_engine.testing import DONE_TURN, ScriptedUsageChatModel


def _open_board(*node_kinds: str) -> BoardGraph:
    nodes: list[BoardNode] = [BoardNode(id="in", kind="incoming")]
    edges: list[BoardEdge] = []
    prev_id = "in"
    prev_handle = "out"
    for idx, kind in enumerate(node_kinds, start=1):
        nid = f"n{idx}"
        nodes.append(BoardNode(id=nid, kind=kind))  # type: ignore[arg-type]
        edges.append(
            BoardEdge(id=f"e{idx}", source=prev_id, source_handle=prev_handle, target=nid)  # type: ignore[arg-type]
        )
        prev_id = nid
        prev_handle = "out" if kind == "text_cleanup" else "safe"
    nodes.append(BoardNode(id="ast", kind="assistant"))
    edges.append(
        BoardEdge(id="elast", source=prev_id, source_handle=prev_handle, target="ast")  # type: ignore[arg-type]
    )
    return BoardGraph(nodes=tuple(nodes), edges=tuple(edges))


_PLACEABLE_CHECKS = (
    "word_filter",
    "text_cleanup",
    "length_limit",
    "secret_scan",
    "ml_classifier",
    "jev",
    "safety_check",
    "llm_review",
    "tool_filter",
)


def _ok_reply() -> ChatCompletion:
    return ChatCompletion(
        text=json.dumps({"reply": "Here you go.", "tool_calls": [], "refused": False}),
        input_tokens=40,
        output_tokens=12,
    )


@pytest.mark.spec("ENG-CAMP-001")
def test_campaign_exposes_19_unique_levels_across_three_difficulties() -> None:
    # Spec 0051 replaced the 23 levels with 19 (ENG-LADDER-001).
    levels = get_levels()
    assert len(levels) == 19
    assert tuple(lvl.id for lvl in levels) == game_mod.ALL_LEVEL_IDS
    assert len({lvl.title for lvl in levels}) == 19
    assert [lvl.order for lvl in levels] == list(range(1, 20))
    by_diff = game_mod.LEVEL_IDS_BY_DIFFICULTY
    for difficulty, count, free, tier in (
        ("Easy", 5, 3, None),
        ("Medium", 7, 2, "standard"),
        ("Hard", 7, 0, "budget"),
    ):
        group = [lvl for lvl in levels if lvl.difficulty == difficulty]
        assert len(group) == count
        assert [lvl.tier for lvl in group].count("free") == free
        assert all(lvl.agent_tier == tier for lvl in group)
        assert tuple(lvl.id for lvl in group) == by_diff[difficulty]
    for lvl in levels:
        assert lvl.follow_up is not None
        assert any(m.is_attack for m in lvl.messages)
        assert any(not m.is_attack for m in lvl.messages)


@pytest.mark.spec("ENG-CAMP-002")
async def test_level_constraints_reject_invalid_boards_and_penalize_sla_violations() -> None:
    validate_board_for_level = game_mod.validate_board_for_level

    easy_4 = get_level("easy-4")
    assert "word_filter" in easy_4.constraints.disabled_checks
    with pytest.raises(BoardValidationError, match="word_filter"):
        validate_board_for_level(_open_board("word_filter"), easy_4)
    with pytest.raises(BoardValidationError):
        await run_wave(_open_board("word_filter"), level_id="easy-4")

    hard_2 = get_level("hard-2")
    assert hard_2.constraints.max_check_nodes == 3
    too_many = _open_board("word_filter", "length_limit", "secret_scan", "text_cleanup")
    with pytest.raises(BoardValidationError, match="3"):
        validate_board_for_level(too_many, hard_2)

    # The cost budget of medium-5 stops a board that reviews every prompt (ENG-FAIR-010).
    medium_5 = get_level("medium-5")
    assert medium_5.constraints.max_total_cost_usd is not None
    review = ScriptedUsageChatModel(
        replies=[], default=ChatCompletion(text=json.dumps({"blocked": False, "reason": "ok"}))
    )
    result = await run_wave(_open_board("llm_review"), level_id="medium-5", check_model=review)
    assert result.stop is not None
    assert result.stop.reason == "budget"
    assert result.score.constraint_violations
    assert result.score.won is False
    assert result.score.total_score == 0


@pytest.mark.spec("ENG-CAMP-005")
@pytest.mark.parametrize(
    ("level_id", "taught"),
    [
        ("easy-2", ("text_cleanup", "secret_scan", "word_filter", "length_limit")),
        ("easy-4", ("ml_classifier",)),
    ],
)
async def test_intro_levels_disable_every_check_except_the_ones_they_teach(
    level_id: str, taught: tuple[str, ...]
) -> None:
    level = get_level(level_id)
    others = {k for k in _PLACEABLE_CHECKS if k not in taught}

    assert set(level.constraints.disabled_checks) == others
    for kind in sorted(others):
        with pytest.raises(BoardValidationError, match=kind):
            game_mod.validate_board_for_level(_open_board(kind), level)
    game_mod.validate_board_for_level(_open_board(*taught), level)


@pytest.mark.spec("ENG-CAMP-005")
async def test_easy_2_is_winnable_with_only_text_cleaner_and_secret_scanner() -> None:
    from shield_engine.game.calibration import reference, run_plan

    board = reference("easy-2").board
    assert {n.kind for n in board.board.nodes} == {
        "incoming",
        "text_cleanup",
        "secret_scan",
        "assistant",
    }
    result = await run_plan("easy-2", board)
    assert result.score.won is True


@pytest.mark.spec("ENG-CAMP-003")
async def test_follow_up_challenge_evaluates_on_single_run_with_no_extra_model_calls() -> None:
    from shield_engine.game.calibration import BoardPlan, reference, run_plan

    # easy-1 mastery: 2 check nodes or fewer.
    ref = reference("easy-1").board
    passed = await run_plan("easy-1", ref)
    assert passed.score.won is True
    assert passed.score.follow_up_passed is True
    assert passed.score.follow_up_feedback == ""

    checks = [n for n in ref.board.nodes if n.kind not in {"incoming", "assistant"}]
    extra = BoardNode(id="len2", kind="length_limit", config={"max_chars": 100_000})
    missed = await run_plan("easy-1", BoardPlan(chain(*checks, extra)))
    assert missed.score.won is True
    assert missed.score.follow_up_passed is False
    assert missed.score.follow_up_feedback

    lost = await run_wave(_open_board(), level_id="easy-1")
    assert lost.score.won is False
    assert lost.score.follow_up_passed is False

    # medium-2 mastery forbids LLM review; the follow-up makes no extra model call. (Medium 1
    # has no model checks since spec 0051 calibration.)
    medium_2 = get_level("medium-2")
    rules = [str(r) for r in reference("medium-2").board.board.nodes[-1].config["rules"]]
    review_board = chain(
        BoardNode(id="ar", kind="llm_review", config={"prompt": "Stop attacks."}), rules=rules
    )
    checker = ScriptedUsageChatModel(
        replies=[
            ChatCompletion(text=json.dumps({"blocked": m.is_attack, "reason": "checked"}))
            for m in medium_2.messages
        ]
    )
    # Each prompt that calls a tool gets a closing second turn (ENG-LADDER-012).
    responder = ScriptedUsageChatModel(
        replies=[
            turn
            for m in medium_2.messages
            if not m.is_attack
            for turn in (
                ChatCompletion(
                    text=json.dumps(
                        {"reply": "OK", "tool_calls": [{"name": m.expected_tool}], "refused": False}
                    )
                ),
                DONE_TURN,
            )
        ]
    )
    res_med = await run_wave(
        review_board, level_id="medium-2", agent=responder, check_model=checker
    )
    assert len(checker.calls) == len(medium_2.messages)
    assert len(responder.calls) == 2 * sum(1 for m in medium_2.messages if not m.is_attack)
    assert res_med.score.won is True
    assert res_med.score.follow_up_passed is False
    assert "llm_review" in res_med.score.follow_up_feedback


@pytest.mark.spec("ENG-CAMP-004")
async def test_dual_use_tool_requires_selective_gating_across_prompts() -> None:
    # hard-5: approve_expense is right with proof and a small amount, wrong otherwise.
    from shield_engine.game.calibration import reference, run_plan

    ref = reference("hard-5")
    assert (await run_plan("hard-5", ref.board)).score.won is True
    for plan in ref.dual_use.values():
        assert (await run_plan("hard-5", plan)).score.won is False


@pytest.mark.spec("ENG-SUPA-001")
def test_campaign_messages_use_postgres_instead_of_legacy_embedded_db() -> None:
    easy_3 = get_level("easy-3")
    assert any("pg_catalog.pg_tables" in msg.text and not msg.is_attack for msg in easy_3.messages)
    legacy = "sql" + "ite"
    for lvl in get_levels():
        for msg in lvl.messages:
            assert legacy not in msg.text.lower()
