from fastapi import APIRouter

from shield_api.dependencies import ContainerDep
from shield_api.schemas import FeedbackRequest, FeedbackResponse

router = APIRouter(tags=["Feedback"])


@router.post("/feedback")
async def feedback(request: FeedbackRequest, container: ContainerDep) -> FeedbackResponse:
    """Record a reviewer's label: it overrides the classifier and nudges the model."""
    container.classifier.learn(request.prompt, request.human_label)
    if request.request_id:
        await container.audit_log.review(request.request_id, request.human_label)
    return FeedbackResponse(status="success")
