from fastapi import APIRouter

from shield_api.dependencies import ClearanceDep, ContainerDep
from shield_api.schemas import PredictRequest, PredictResponse, ScreenRequest, ScreenResponse
from shield_api.services.access import config_for_mode
from shield_engine import ScreeningContext, Verdict

router = APIRouter(tags=["Screening"])


@router.post("/predict")
async def predict(request: PredictRequest, container: ContainerDep) -> PredictResponse:
    """Layer 1 only: the classifier's verdict, no LLM calls."""
    signal = container.classifier.score(request.message)
    return PredictResponse(
        verdict=signal.verdict,
        confidence_score=signal.score,
        is_malicious=signal.verdict is Verdict.MALICIOUS,
        override=signal.override,
    )


@router.post("/screen")
async def screen(
    request: ScreenRequest, container: ContainerDep, clearance: ClearanceDep
) -> ScreenResponse:
    """The full engine decision, without running the demo assistant."""
    decision = await container.shield.screen(
        request.message,
        ScreeningContext(clearance=clearance),
        config=config_for_mode(request.mode, container.shield.config),
    )
    return ScreenResponse(
        verdict=decision.verdict,
        policy=decision.policy,
        blocked=decision.blocked,
        layer=decision.layer,
        reason=decision.reason,
        ml_confidence=decision.classifier.score,
        adjudicated=decision.adjudication is not None,
    )
