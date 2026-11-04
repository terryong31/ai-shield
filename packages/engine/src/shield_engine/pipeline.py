"""The :class:`Shield` orchestrator: routes a prompt through the layers to a decision."""

from __future__ import annotations

from collections.abc import AsyncIterator

from shield_engine.adjudication.fallback import fallback_adjudication
from shield_engine.config import ShieldConfig
from shield_engine.events import (
    ClassifierScored,
    DebateTurn,
    DecisionMade,
    ModerationFlagged,
    ShieldEvent,
    StageStarted,
)
from shield_engine.ports import Adjudicator, Classifier, Moderator
from shield_engine.types import (
    Adjudication,
    Clearance,
    Decision,
    DecisionLayer,
    ModerationResult,
    ScreeningContext,
    Signal,
    Stage,
    ToolPolicy,
    Verdict,
)

_SKIPPED_SIGNAL = Signal(
    detector="classifier", verdict=Verdict.SAFE, score=0.0, details={"skipped": True}
)


class Shield:
    def __init__(
        self,
        classifier: Classifier,
        *,
        moderator: Moderator | None = None,
        adjudicator: Adjudicator | None = None,
        config: ShieldConfig | None = None,
    ) -> None:
        self.classifier = classifier
        self.moderator = moderator
        self.adjudicator = adjudicator
        self.config = config or ShieldConfig()

    async def screen(
        self,
        prompt: str,
        context: ScreeningContext | None = None,
        *,
        config: ShieldConfig | None = None,
    ) -> Decision:
        """Screen ``prompt`` and return only the final decision."""
        async for event in self.screen_stream(prompt, context, config=config):
            if isinstance(event, DecisionMade):
                return event.decision
        raise RuntimeError("screen_stream ended without a decision")  # pragma: no cover

    async def screen_stream(
        self,
        prompt: str,
        context: ScreeningContext | None = None,
        *,
        config: ShieldConfig | None = None,
    ) -> AsyncIterator[ShieldEvent]:
        """Screen ``prompt``, yielding progress events and finally one ``DecisionMade``."""
        context = context or ScreeningContext()
        config = config or self.config

        yield StageStarted(Stage.CLASSIFIER)
        signal = _SKIPPED_SIGNAL if config.skip_classifier else self.classifier.score(prompt)
        yield ClassifierScored(signal)

        routed = signal.verdict
        moderation: ModerationResult | None = None
        if self.moderator is not None:
            moderation = await self.moderator.moderate(prompt)
            if moderation.flagged:
                yield ModerationFlagged(moderation)
                # Moderation can only escalate, never relax, a verdict.
                if routed is not Verdict.MALICIOUS:
                    routed = Verdict.UNCERTAIN

        if routed is Verdict.MALICIOUS:
            yield DecisionMade(
                Decision(
                    verdict=Verdict.MALICIOUS,
                    policy=ToolPolicy.SHUTDOWN,
                    blocked=True,
                    layer=DecisionLayer.CLASSIFIER,
                    reason="High confidence ML threat detection",
                    classifier=signal,
                    moderation=moderation,
                )
            )
            return

        needs_adjudication = (
            routed is Verdict.UNCERTAIN
            or config.always_adjudicate
            or context.clearance is not Clearance.NONE
        )
        if not needs_adjudication:
            yield DecisionMade(
                Decision(
                    verdict=routed,
                    policy=config.default_policy,
                    blocked=False,
                    layer=DecisionLayer.PASSTHROUGH,
                    reason="Passed Layer 1 screening",
                    classifier=signal,
                    moderation=moderation,
                )
            )
            return

        yield StageStarted(Stage.ADJUDICATION)
        adjudication: Adjudication | None = None
        if self.adjudicator is None:
            adjudication = fallback_adjudication(
                context.clearance, "No adjudicator configured; conservative policy applied."
            )
        else:
            async for item in self.adjudicator.adjudicate(prompt, context.clearance):
                if isinstance(item, Adjudication):
                    adjudication = item
                else:
                    yield DebateTurn(item)
            if adjudication is None:  # pragma: no cover - adjudicator contract violation
                adjudication = fallback_adjudication(
                    context.clearance, "Adjudicator returned no verdict; conservative policy."
                )

        blocked = adjudication.verdict is Verdict.MALICIOUS
        yield DecisionMade(
            Decision(
                verdict=adjudication.verdict,
                policy=ToolPolicy.SHUTDOWN if blocked else adjudication.policy,
                blocked=blocked,
                layer=DecisionLayer.ADJUDICATION,
                reason=adjudication.summary,
                classifier=signal,
                moderation=moderation,
                adjudication=adjudication,
            )
        )
