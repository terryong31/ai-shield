from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from shield_api.dependencies import ClearanceDep, ContainerDep
from shield_api.schemas import (
    BoardGraphSchema,
    CheckDefinitionSchema,
    GameCatalogResponse,
    GameLevelSchema,
    GameRunRequest,
    GameRunResponse,
    GameTrainRequest,
    GameTrainResponse,
    LevelId,
    MessageTraceSchema,
    ScoreCreateRequest,
    ScoreRecord,
    WaveScoreSchema,
)
from shield_engine import Clearance
from shield_engine.game import (
    BoardEdge,
    BoardGraph,
    BoardNode,
    BoardValidationError,
    evaluate_message,
    get_check_catalog,
    get_levels,
    run_wave,
    score_wave,
    train_custom_classifier,
)

router = APIRouter(prefix="/game", tags=["Game"])


def _to_engine_board(schema: BoardGraphSchema) -> BoardGraph:
    return BoardGraph(
        nodes=tuple(BoardNode(id=n.id, kind=n.kind, config=dict(n.config)) for n in schema.nodes),
        edges=tuple(
            BoardEdge(
                id=e.id,
                source=e.source,
                source_handle=e.source_handle,
                target=e.target,
            )
            for e in schema.edges
        ),
    )


@router.get("/levels")
async def list_game_levels() -> GameCatalogResponse:
    """Return built-in levels and placeable check definitions."""
    levels = [GameLevelSchema.model_validate(asdict(lvl)) for lvl in get_levels()]
    checks = [CheckDefinitionSchema.model_validate(asdict(chk)) for chk in get_check_catalog()]
    return GameCatalogResponse(levels=levels, checks=checks)


@router.post(
    "/run",
    responses={422: {"description": "Invalid board graph"}},
)
async def run_game_board(body: GameRunRequest, container: ContainerDep) -> GameRunResponse:
    """Run either a full level wave or a single custom message against a player's board."""
    board = _to_engine_board(body.board)
    try:
        if body.custom_message is not None:
            trace = await evaluate_message(
                board,
                message=body.custom_message,
                message_id="custom",
                is_attack=True,
                classifier=container.classifier,
            )
            blocked = 1 if trace.outcome == "blocked" else 0
            wave_score = score_wave(
                attacks_blocked=blocked,
                attacks_total=1,
                benign_passed=1,
                benign_total=1,
                avg_latency_ms=trace.total_latency_ms,
                max_latency_ms=300.0,
                total_cost_usd=trace.total_cost_usd,
                max_cost_usd=0.01,
            )
            return GameRunResponse(
                level_id=body.level_id,
                traces=[MessageTraceSchema.model_validate(asdict(trace))],
                score=WaveScoreSchema.model_validate(asdict(wave_score)),
            )

        result = await run_wave(
            board,
            level_id=body.level_id,
            classifier=container.classifier,
        )
    except BoardValidationError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err

    return GameRunResponse(
        level_id=result.level_id,
        traces=[MessageTraceSchema.model_validate(asdict(t)) for t in result.traces],
        score=WaveScoreSchema.model_validate(asdict(result.score)),
    )


@router.get("/scores")
async def list_game_scores(
    container: ContainerDep,
    level_id: LevelId | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[ScoreRecord]:
    """List top scoreboard records ordered by score, speed, and cost."""
    return await container.audit_log.list_scores(level_id=level_id, limit=limit)


@router.post("/scores")
async def create_game_score(body: ScoreCreateRequest, container: ContainerDep) -> ScoreRecord:
    """Save a completed run to the scoreboard."""
    return await container.audit_log.record_score(body)


@router.delete(
    "/scores",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"description": "Admin access required."}},
)
async def clear_game_scores(clearance: ClearanceDep, container: ContainerDep) -> Response:
    """Clear scoreboard records. Requires an active admin clearance session."""
    if clearance is not Clearance.GRANTED:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin access required.")
    await container.audit_log.clear_scores()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/train",
    responses={422: {"description": "Invalid algorithm or dataset"}},
)
async def train_game_classifier(body: GameTrainRequest) -> GameTrainResponse:
    """Validate and train an allowlisted ML classifier on uploaded CSV or dataset rows."""
    try:
        summary = train_custom_classifier(
            algorithm=body.algorithm,
            dataset=body.dataset,
            csv_text=body.csv_text,
        )
    except BoardValidationError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err
    return GameTrainResponse(
        algorithm=summary.algorithm,
        sample_count=summary.sample_count,
        accuracy=summary.accuracy,
        dataset=list(summary.dataset),
    )
