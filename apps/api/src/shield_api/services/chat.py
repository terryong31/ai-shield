"""The /chat flow: engine events → wire events, then the demo assistant."""

import logging
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from shield_api.container import Container
from shield_api.demo.tools import CATALOGUE
from shield_api.schemas import (
    BlockEvent,
    ChatRequest,
    DebateTurnEvent,
    ErrorEvent,
    FinalResponseEvent,
    MlResultEvent,
    ModerationEvent,
    PolicyUpdateEvent,
    StageChangeEvent,
    StartEvent,
    ToolEndEvent,
    ToolStartEvent,
)
from shield_api.services.access import config_for_mode
from shield_engine import (
    Clearance,
    Decision,
    ScreeningContext,
    ShieldConfig,
    Stage,
    allowed_tools,
)
from shield_engine.events import (
    ClassifierScored,
    DebateTurn,
    DecisionMade,
    ModerationFlagged,
    StageStarted,
)

logger = logging.getLogger(__name__)

GENERIC_ERROR = "The request could not be processed. The incident has been logged."

_STAGES = {Stage.CLASSIFIER: "ml_processing", Stage.ADJUDICATION: "debate"}


def _metadata(request: ChatRequest, decision: Decision, clearance: Clearance) -> dict[str, Any]:
    adjudication = decision.adjudication
    return {
        "mlConfidence": decision.classifier.score,
        "generated_intent": decision.classifier.verdict.value,
        "dualAgentTriggered": adjudication is not None,
        "agentAnalysis": adjudication.analysis if adjudication else None,
        "agentDialogue": [
            {"agent": t.agent.value, "message": t.message, "timestamp": t.timestamp}
            for t in (adjudication.dialogue if adjudication else ())
        ],
        "moderationCategories": list(decision.moderation.categories) if decision.moderation else [],
        "toolPolicy": decision.policy.value,
        "mode": request.mode,
        "clearance": clearance.value,
    }


async def chat_events(
    request: ChatRequest, container: Container, clearance: Clearance
) -> AsyncIterator[BaseModel]:
    try:
        yield StartEvent(query=request.message)

        context = ScreeningContext(clearance=clearance)
        config: ShieldConfig = config_for_mode(request.mode, container.shield.config)

        decision: Decision | None = None
        async for event in container.shield.screen_stream(request.message, context, config=config):
            match event:
                case StageStarted(stage=stage):
                    yield StageChangeEvent(stage=_STAGES[stage])  # type: ignore[arg-type]
                case ClassifierScored(signal=signal):
                    yield MlResultEvent(confidence=signal.score, verdict=signal.verdict)
                case ModerationFlagged(result=result):
                    yield ModerationEvent(safe=False, categories=list(result.categories))
                case DebateTurn(turn=turn):
                    yield DebateTurnEvent(agent=turn.agent.value, message=turn.message)
                case DecisionMade(decision=final):
                    decision = final
        assert decision is not None
        metadata = _metadata(request, decision, clearance)

        if decision.blocked:
            yield BlockEvent(reason=decision.reason, layer=decision.layer)
            yield StageChangeEvent(stage="final")
            await container.audit_log.record(
                query=request.message,
                action="BLOCKED",
                reason=decision.reason,
                layer=decision.layer.value,
                metadata=metadata,
            )
            return

        permitted = allowed_tools(decision.policy, (tool.spec for tool in CATALOGUE))
        yield StageChangeEvent(stage="final")
        yield PolicyUpdateEvent(policy=decision.policy, allowed_tools=permitted)

        reply = await container.assistant.respond(request.message, permitted)
        for call in reply.tool_calls:
            yield ToolStartEvent(tool=call.tool, args=call.args)
            yield ToolEndEvent(tool=call.tool, result=call.result)

        await container.audit_log.record(
            query=request.message,
            action="ALLOWED",
            reason=decision.reason,
            layer=decision.layer.value,
            metadata={
                **metadata,
                "allowedTools": permitted,
                "tool_calls": [c.tool for c in reply.tool_calls],
                "aiResponse": reply.text,
            },
        )
        yield FinalResponseEvent(text=reply.text)
    except Exception:
        logger.exception("chat stream failed")
        yield ErrorEvent(message=GENERIC_ERROR)
