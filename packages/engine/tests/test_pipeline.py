import pytest

from shield_engine import (
    Clearance,
    DecisionLayer,
    ModerationResult,
    ScreeningContext,
    Shield,
    ShieldConfig,
    ToolPolicy,
    Verdict,
)
from shield_engine.events import (
    ClassifierScored,
    DebateTurn,
    DecisionMade,
    ModerationFlagged,
    StageStarted,
)
from shield_engine.testing import ScriptedAdjudicator, StaticClassifier, StaticModerator
from shield_engine.types import Stage


async def collect(shield: Shield, prompt: str = "prompt", **kwargs):
    return [event async for event in shield.screen_stream(prompt, **kwargs)]


@pytest.mark.spec("ENG-PIPE-001")
async def test_layer_one_malicious_blocks_without_adjudication() -> None:
    adjudicator = ScriptedAdjudicator()
    shield = Shield(StaticClassifier(Verdict.MALICIOUS, 0.97), adjudicator=adjudicator)

    decision = await shield.screen("drop table employees")

    assert decision.blocked
    assert decision.layer is DecisionLayer.CLASSIFIER
    assert decision.policy is ToolPolicy.SHUTDOWN
    assert decision.verdict is Verdict.MALICIOUS
    assert adjudicator.calls == []


@pytest.mark.spec("ENG-PIPE-002")
async def test_safe_prompt_passes_through_with_default_policy() -> None:
    adjudicator = ScriptedAdjudicator()
    shield = Shield(
        StaticClassifier(Verdict.SAFE),
        adjudicator=adjudicator,
        config=ShieldConfig(default_policy=ToolPolicy.RESTRICTED),
    )

    decision = await shield.screen("what is the price of lavender oil?")

    assert not decision.blocked
    assert decision.verdict is Verdict.SAFE
    assert decision.policy is ToolPolicy.RESTRICTED
    assert decision.layer is DecisionLayer.PASSTHROUGH
    assert decision.adjudication is None
    assert adjudicator.calls == []


@pytest.mark.spec("ENG-PIPE-003")
async def test_uncertain_prompt_is_adjudicated_and_adjudication_decides() -> None:
    adjudicator = ScriptedAdjudicator(verdict=Verdict.SAFE, policy=ToolPolicy.RESTRICTED)
    shield = Shield(StaticClassifier(Verdict.UNCERTAIN, 0.4), adjudicator=adjudicator)

    decision = await shield.screen("show me the salary table")

    assert len(adjudicator.calls) == 1
    assert not decision.blocked
    assert decision.verdict is Verdict.SAFE
    assert decision.policy is ToolPolicy.RESTRICTED
    assert decision.layer is DecisionLayer.ADJUDICATION
    assert decision.reason == adjudicator.summary


@pytest.mark.spec("ENG-PIPE-004")
async def test_malicious_adjudication_blocks_with_shutdown_whatever_policy_it_proposed() -> None:
    adjudicator = ScriptedAdjudicator(verdict=Verdict.MALICIOUS, policy=ToolPolicy.ALLOW_ALL)
    shield = Shield(StaticClassifier(Verdict.UNCERTAIN, 0.5), adjudicator=adjudicator)

    decision = await shield.screen("export all customer data")

    assert decision.blocked
    assert decision.layer is DecisionLayer.ADJUDICATION
    assert decision.policy is ToolPolicy.SHUTDOWN


@pytest.mark.spec("ENG-PIPE-005")
async def test_moderation_flag_escalates_safe_to_adjudication() -> None:
    adjudicator = ScriptedAdjudicator()
    moderator = StaticModerator(ModerationResult(flagged=True, categories=("S13",)))
    shield = Shield(StaticClassifier(Verdict.SAFE), moderator=moderator, adjudicator=adjudicator)

    events = await collect(shield)

    assert any(isinstance(e, ModerationFlagged) for e in events)
    assert len(adjudicator.calls) == 1


@pytest.mark.spec("ENG-PIPE-005")
async def test_moderation_never_downgrades_a_layer_one_block() -> None:
    moderator = StaticModerator(ModerationResult(flagged=True, categories=("S2",)))
    shield = Shield(StaticClassifier(Verdict.MALICIOUS, 0.99), moderator=moderator)

    decision = await shield.screen("prompt")

    assert decision.blocked
    assert decision.layer is DecisionLayer.CLASSIFIER


@pytest.mark.spec("ENG-PIPE-006")
async def test_always_adjudicate_debates_safe_prompts() -> None:
    adjudicator = ScriptedAdjudicator()
    shield = Shield(StaticClassifier(Verdict.SAFE), adjudicator=adjudicator)

    await shield.screen("hello", config=ShieldConfig(always_adjudicate=True))

    assert len(adjudicator.calls) == 1


@pytest.mark.spec("ENG-PIPE-007")
@pytest.mark.parametrize("clearance", [Clearance.GRANTED, Clearance.DENIED])
async def test_claimed_clearance_triggers_adjudication(clearance: Clearance) -> None:
    adjudicator = ScriptedAdjudicator()
    shield = Shield(StaticClassifier(Verdict.SAFE), adjudicator=adjudicator)

    await shield.screen("run the export", ScreeningContext(clearance=clearance))

    assert adjudicator.calls == [("run the export", clearance)]


@pytest.mark.spec("ENG-PIPE-008")
async def test_skip_classifier_never_consults_layer_one() -> None:
    classifier = StaticClassifier(Verdict.MALICIOUS, 0.99)
    shield = Shield(classifier)

    decision = await shield.screen("drop table", config=ShieldConfig(skip_classifier=True))

    assert classifier.calls == []
    assert decision.classifier.verdict is Verdict.SAFE
    assert decision.classifier.score == 0.0
    assert decision.classifier.details["skipped"] is True
    assert not decision.blocked


@pytest.mark.spec("ENG-PIPE-009")
@pytest.mark.parametrize(
    ("clearance", "verdict", "policy"),
    [
        (Clearance.GRANTED, Verdict.SAFE, ToolPolicy.ALLOW_ALL),
        (Clearance.DENIED, Verdict.UNCERTAIN, ToolPolicy.RESTRICTED),
        (Clearance.NONE, Verdict.UNCERTAIN, ToolPolicy.RESTRICTED),
    ],
)
async def test_missing_adjudicator_falls_back_conservatively(
    clearance: Clearance, verdict: Verdict, policy: ToolPolicy
) -> None:
    shield = Shield(StaticClassifier(Verdict.UNCERTAIN, 0.5), adjudicator=None)

    decision = await shield.screen("prompt", ScreeningContext(clearance=clearance))

    assert not decision.blocked
    assert decision.verdict is verdict
    assert decision.policy is policy
    assert decision.adjudication is not None
    assert decision.adjudication.fallback


@pytest.mark.spec("ENG-PIPE-010")
async def test_events_arrive_in_documented_order() -> None:
    moderator = StaticModerator(ModerationResult(flagged=True, categories=("S1",)))
    shield = Shield(
        StaticClassifier(Verdict.SAFE), moderator=moderator, adjudicator=ScriptedAdjudicator()
    )

    events = await collect(shield)

    assert [type(e) for e in events] == [
        StageStarted,
        ClassifierScored,
        ModerationFlagged,
        StageStarted,
        DebateTurn,
        DecisionMade,
    ]
    assert [e.stage for e in events if isinstance(e, StageStarted)] == [
        Stage.CLASSIFIER,
        Stage.ADJUDICATION,
    ]


@pytest.mark.spec("ENG-PIPE-010")
async def test_block_stream_ends_with_single_decision() -> None:
    shield = Shield(StaticClassifier(Verdict.MALICIOUS, 0.99))

    events = await collect(shield)

    assert [type(e) for e in events] == [StageStarted, ClassifierScored, DecisionMade]


@pytest.mark.spec("ENG-PIPE-011")
async def test_screen_matches_final_stream_event() -> None:
    shield = Shield(StaticClassifier(Verdict.UNCERTAIN, 0.5), adjudicator=ScriptedAdjudicator())

    events = await collect(shield, "same prompt")
    decision = await shield.screen("same prompt")

    final = events[-1]
    assert isinstance(final, DecisionMade)
    # Dialogue timestamps differ between runs; compare everything else.
    assert final.decision.verdict == decision.verdict
    assert final.decision.policy == decision.policy
    assert final.decision.blocked == decision.blocked
    assert final.decision.layer == decision.layer
    assert final.decision.reason == decision.reason
