from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from shield_api.dependencies import ClearanceDep, ContainerDep
from shield_api.schemas import ChatRequest
from shield_api.services.chat import chat_events

router = APIRouter(tags=["Chat"])

NDJSON = "application/x-ndjson"


@router.post(
    "/chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "A stream of `ChatEvent` objects, one JSON document per line.",
            "content": {NDJSON: {"schema": {"$ref": "#/components/schemas/ChatEvent"}}},
        }
    },
)
async def chat(
    request: ChatRequest, container: ContainerDep, clearance: ClearanceDep
) -> StreamingResponse:
    """Screen the prompt, then run the demo assistant under the resulting tool policy."""

    async def ndjson() -> AsyncIterator[str]:
        async for event in chat_events(request, container, clearance):
            yield event.model_dump_json() + "\n"

    return StreamingResponse(ndjson(), media_type=NDJSON, headers={"Cache-Control": "no-cache"})
