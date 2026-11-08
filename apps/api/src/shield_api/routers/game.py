import logging
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from shield_api.container import Container
from shield_api.demo.byok import ProviderAuthError
from shield_api.dependencies import PLAYER_SESSION_COOKIE, ClearanceDep, ContainerDep
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
    PlayerSessionStatus,
    RunLevelId,
    SavedBoardRequest,
    SavedBoardResponse,
    ScoreCreateRequest,
    ScoreRecord,
    WaveScoreSchema,
)
from shield_api.services.players import AI_AGENT_NODE_KINDS, QuotaExceededError
from shield_engine import Clearance
from shield_engine.game import (
    AgentProfile,
    AgentTool,
    AgentUnavailableError,
    BoardEdge,
    BoardGraph,
    BoardNode,
    BoardValidationError,
    get_check_catalog,
    get_level,
    get_levels,
    run_single_message,
    run_wave,
    train_custom_classifier,
    validate_board,
)
from shield_engine.game.custom import (
    build_custom_messages,
    run_custom_message,
    run_custom_wave,
    validate_custom_profile,
)

logger = logging.getLogger(__name__)

BYOK_KEY_MAX_CHARS = 200

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
    responses={
        403: {"description": "Sign in required for AI agent nodes."},
        422: {"description": "Invalid board graph"},
        429: {"description": "Daily run limit reached."},
        502: {
            "description": "Custom mode: the player's model provider failed or rejected the key."
        },
        503: {"description": "The AI Agent model is unavailable; the run was not counted."},
    },
)
async def run_game_board(
    body: GameRunRequest, request: Request, container: ContainerDep
) -> GameRunResponse:
    """Run either a full level wave or a single custom message against a player's board."""
    board = _to_engine_board(body.board)
    try:
        validate_board(board)
    except BoardValidationError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err

    token = request.cookies.get(PLAYER_SESSION_COOKIE)
    player = await container.players.lookup(token)
    uses_ai_nodes = any(node.kind in AI_AGENT_NODE_KINDS for node in board.nodes)
    if uses_ai_nodes and not player.ai_nodes_allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Sign in required to use AI agent nodes (safety_check, agent_review).",
        )

    if body.level_id == "custom":
        return await _run_custom(body, board, player, container)

    is_custom_test = body.custom_message is not None
    # A classification-only level calls no model, so it costs no quota (spec 0021).
    counts_quota = get_level(body.level_id).agent is not None
    if counts_quota:
        try:
            player = await container.players.check_run(token, is_custom_test=is_custom_test)
        except QuotaExceededError as err:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(err)) from err

    try:
        if body.custom_message is not None:
            result = await run_single_message(
                board,
                level_id=body.level_id,
                message=body.custom_message,
                classifier=container.classifier,
                agent=container.game_agent,
                agents=container.game_agents,
            )
        else:
            result = await run_wave(
                board,
                level_id=body.level_id,
                classifier=container.classifier,
                agent=container.game_agent,
                agents=container.game_agents,
            )
    except BoardValidationError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err
    except AgentUnavailableError as err:
        logger.exception("Game AI Agent model failed; run not counted")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The AI Agent is unavailable right now. This run was not counted.",
        ) from err

    # Charged only after a successful run, so provider failures never cost a run.
    if counts_quota:
        try:
            await container.players.consume_run(token, is_custom_test=is_custom_test)
        except QuotaExceededError as err:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(err)) from err

    score_schema = WaveScoreSchema.model_validate(asdict(result.score))
    # Simulated agent runs are practice; live and model-free (Easy) runs are recorded.
    recordable = result.agent_mode in ("live", "none")
    if not is_custom_test and player.can_record_scores and recordable:
        await container.audit_log.record_score(
            ScoreCreateRequest(
                player_name=player.player_name,
                level_id=body.level_id,
                total_score=score_schema.total_score,
                medal=score_schema.medal,
                attacks_blocked=score_schema.attacks_protected,
                attacks_total=score_schema.attacks_total,
                false_alarms=score_schema.false_alarms,
                avg_latency_ms=score_schema.avg_latency_ms,
                total_cost_usd=score_schema.total_cost_usd,
                board=body.board,
            )
        )

    return GameRunResponse(
        level_id=result.level_id,
        traces=[MessageTraceSchema.model_validate(asdict(t)) for t in result.traces],
        score=score_schema,
        agent_mode=result.agent_mode,
    )


async def _run_custom(
    body: GameRunRequest,
    board: BoardGraph,
    player: PlayerSessionStatus,
    container: Container,
) -> GameRunResponse:
    """Custom sandbox (spec 0022): the player's agent, dataset and key, for paid players.

    Runs use the player's own key, so they cost no quota, and they are never recorded.
    """
    if player.tier != "paid":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Custom mode is for paid players.")
    custom = body.custom
    if custom is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Custom mode needs an agent, dataset and model."
        )
    api_key = custom.model.api_key.get_secret_value()
    if not api_key.strip() or len(api_key) > BYOK_KEY_MAX_CHARS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The API key must be 1 to 200 characters."
        )
    profile = AgentProfile(
        objective=custom.agent.objective,
        tools=tuple(AgentTool(t.name, t.description, t.allowed) for t in custom.agent.tools),
        token_budget=0,
    )
    try:
        validate_custom_profile(profile)
        messages = build_custom_messages([row.model_dump() for row in custom.dataset], profile)
    except BoardValidationError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err

    model = container.byok_factory(custom.model.provider, custom.model.model, api_key)
    try:
        if body.custom_message is not None:
            result = await run_custom_message(
                board,
                profile=profile,
                message=body.custom_message,
                agent=model,
                classifier=container.classifier,
            )
        else:
            result = await run_custom_wave(
                board,
                profile=profile,
                messages=messages,
                agent=model,
                classifier=container.classifier,
            )
    except AgentUnavailableError as err:
        cause = err.__cause__
        # Log the error type only: provider messages can echo the key.
        logger.warning("Custom sandbox model failed (%s)", type(cause).__name__)
        detail = (
            "The model provider rejected the API key."
            if isinstance(cause, ProviderAuthError)
            else "The model provider did not respond."
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from None

    return GameRunResponse(
        level_id=result.level_id,
        traces=[MessageTraceSchema.model_validate(asdict(t)) for t in result.traces],
        score=WaveScoreSchema.model_validate(asdict(result.score)),
        agent_mode=result.agent_mode,
    )


SAVE_MAX_BYTES = 256 * 1024
SAVE_MAX_NODES = 60
SAVE_MAX_EDGES = 200
SIGN_IN_TO_SAVE = "Sign in to save your board."


async def _saving_email(request: Request, container: Container, level_id: RunLevelId) -> str:
    """The signed-in player's email that keys the save; custom needs a paid plan (spec 0023)."""
    player = await container.players.lookup(request.cookies.get(PLAYER_SESSION_COOKIE))
    if not player.authenticated or player.is_anonymous or not player.email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, SIGN_IN_TO_SAVE)
    if level_id == "custom" and player.tier != "paid":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Custom mode is for paid players.")
    return player.email


@router.get(
    "/saves/{level_id}",
    responses={
        403: {"description": "Sign in required (paid plan for custom)."},
        404: {"description": "No board saved for this level."},
    },
)
async def get_saved_board(
    level_id: RunLevelId, request: Request, container: ContainerDep
) -> SavedBoardResponse:
    """Load the player's saved board for a level."""
    email = await _saving_email(request, container, level_id)
    found = await container.players.load_board(email, level_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No board saved for this level.")
    save, updated_at = found
    return SavedBoardResponse.model_validate(
        {**save, "level_id": level_id, "updated_at": updated_at}
    )


@router.put(
    "/saves/{level_id}",
    responses={
        403: {"description": "Sign in required (paid plan for custom)."},
        413: {"description": "The save is over 256 KB."},
        422: {"description": "Invalid save, too many nodes or edges, or a key in the save."},
    },
)
async def put_saved_board(
    level_id: RunLevelId, body: SavedBoardRequest, request: Request, container: ContainerDep
) -> SavedBoardResponse:
    """Save the player's board for a level, replacing any earlier save. Never stores keys."""
    email = await _saving_email(request, container, level_id)
    if len(await request.body()) > SAVE_MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The save is over 256 KB.")
    if len(body.board.nodes) > SAVE_MAX_NODES or len(body.board.edges) > SAVE_MAX_EDGES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"A save holds at most {SAVE_MAX_NODES} nodes and {SAVE_MAX_EDGES} wires.",
        )
    if body.custom is not None and level_id != "custom":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Only custom mode saves an agent setup."
        )
    save = body.model_dump(mode="json")
    updated_at = await container.players.save_board(email, level_id, save)
    return SavedBoardResponse.model_validate(
        {**save, "level_id": level_id, "updated_at": updated_at}
    )


@router.get("/scores")
async def list_game_scores(
    container: ContainerDep,
    level_id: LevelId | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[ScoreRecord]:
    """List top scoreboard records ordered by score, speed, and cost."""
    return await container.audit_log.list_scores(level_id=level_id, limit=limit)


@router.post(
    "/scores",
    responses={403: {"description": "Sign in required to record leaderboard scores."}},
)
async def create_game_score(
    body: ScoreCreateRequest, request: Request, container: ContainerDep
) -> ScoreRecord:
    """Save a completed run to the scoreboard."""
    token = request.cookies.get(PLAYER_SESSION_COOKIE)
    player = await container.players.lookup(token)
    if not player.can_record_scores:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Sign in required to record leaderboard scores.",
        )
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
