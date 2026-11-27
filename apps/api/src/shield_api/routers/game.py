import asyncio
import functools
import logging
import secrets
import sys
from contextlib import nullcontext
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import ValidationError

from shield_api.container import Container
from shield_api.dependencies import (
    PLAYER_SESSION_COOKIE,
    ClearanceDep,
    ContainerDep,
    client_address,
    enforce_rate_limit,
)
from shield_api.providers.byok import ProviderAuthError
from shield_api.schemas import (
    BoardGraphSchema,
    CheckDefinitionSchema,
    DifficultyLeaderboardEntry,
    GameCatalogResponse,
    GameLevelSchema,
    GameRunRequest,
    GameRunResponse,
    GameTrainRequest,
    GameTrainResponse,
    LeaderboardRankResponse,
    MessageTraceSchema,
    PlayerProgressResponse,
    PlayerSessionStatus,
    RunLevelId,
    RunStopSchema,
    SavedBoardRequest,
    SavedBoardResponse,
    ScoreCreateRequest,
    ScoreRecord,
    WaveScoreSchema,
)
from shield_api.services.agent_cache import CachedChatModel, level_canary
from shield_api.services.anonymous_scores import (
    ANONYMOUS_SCORE_TTL,
    pending_score_record,
)
from shield_api.services.audit import audit
from shield_api.services.clearance import Clearance
from shield_api.services.models import (
    CAMPAIGN_TRAIN_MAX_BYTES,
    ModelTooLargeError,
    owner_hash,
    signing_context,
)
from shield_api.services.players import AI_AGENT_NODE_KINDS, QuotaExceededError
from shield_api.services.rate_limit import (
    GAME_RUN_ACTOR_LIMIT,
    GAME_RUN_ACTOR_WINDOW,
    GAME_RUN_IP_LIMIT,
    GAME_RUN_IP_WINDOW,
    GAME_TRAIN_EMAIL_LIMIT,
    GAME_TRAIN_EMAIL_WINDOW,
)
from shield_api.services.scores import build_player_progress
from shield_api.services.spend import SpendBudgetExceededError
from shield_engine.game import (
    ALLOWED_ML_ALGORITHMS,
    AgentProfile,
    AgentTool,
    AgentUnavailableError,
    BoardEdge,
    BoardGraph,
    BoardNode,
    BoardValidationError,
    DifficultyCategory,
    GameLevel,
    LevelId,
    fit_classifier,
    get_check_catalog,
    get_level,
    get_levels,
    parse_dataset_csv,
    run_wave,
    strip_training_data,
    validate_board,
    validate_board_for_level,
    validate_training_rows,
)
from shield_engine.game.custom import (
    build_custom_messages,
    run_custom_message,
    run_custom_wave,
    validate_custom_profile,
)
from shield_engine.ports import JevClient, ProbabilityModel, UsageChatModel

logger = logging.getLogger(__name__)

# Prompts of one wave that wait on the models together, on levels with no limits.
WAVE_CONCURRENCY = 4

BYOK_KEY_MAX_CHARS = 200
MODEL_CHECK_NODE_KINDS = frozenset({"safety_check", "llm_review", "jev"})

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


def _strip_board_schema(board: BoardGraphSchema) -> BoardGraphSchema:
    engine_board = _to_engine_board(board)
    stripped = strip_training_data(engine_board)
    return BoardGraphSchema(
        nodes=[
            {"id": n.id, "kind": n.kind, "config": dict(n.config)}  # type: ignore[misc]
            for n in stripped.nodes
        ],
        edges=list(board.edges),
    )


def _reject_board_dataset(board: BoardGraphSchema) -> None:
    for node in board.nodes:
        if "dataset" in node.config:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Training data is not accepted here. Train the ML filter first.",
            )


async def _load_board_ml_models(
    board: BoardGraph,
    token: str | None,
    player: PlayerSessionStatus,
    container: Container,
) -> tuple[dict[str, ProbabilityModel], list[str]]:
    loaded: dict[str, ProbabilityModel] = {}
    untrained: list[str] = []
    key = container.model_signing_key
    for node in board.nodes:
        if node.kind != "ml_classifier":
            continue
        raw_mid = node.config.get("model_id")
        if (
            isinstance(raw_mid, str)
            and raw_mid
            and token
            and key is not None
            and player.authenticated
            and not player.is_anonymous
        ) and raw_mid not in loaded:
            model = await container.models.get(token, raw_mid, signing_key=key)
            if model is not None:
                loaded[raw_mid] = model
        if not isinstance(raw_mid, str) or raw_mid not in loaded:
            untrained.append(node.id)
    return loaded, untrained


@functools.cache
def _public_catalogue() -> tuple[list[GameLevelSchema], list[CheckDefinitionSchema]]:
    """The levels and checks never change while the process runs, so build them once."""
    levels = [_public_level(lvl) for lvl in get_levels()]
    checks = [CheckDefinitionSchema.model_validate(asdict(chk)) for chk in get_check_catalog()]
    return levels, checks


@router.get("/levels")
async def list_game_levels(container: ContainerDep, response: Response) -> GameCatalogResponse:
    """Return built-in levels and placeable check definitions."""
    levels, checks = _public_catalogue()
    # Public and the same for everyone: the CDN can serve it without calling the gateway.
    response.headers["Cache-Control"] = "public, s-maxage=300, stale-while-revalidate=86400"
    return GameCatalogResponse(
        levels=levels,
        checks=checks,
        jev_key_configured=container.jev_client is not None,
        ai_key_configured=bool(container.game_agent or container.game_agents),
        self_upgrade_enabled=container.settings.ALLOW_SELF_UPGRADE,
        billing_enabled=container.payments is not None,
    )


@router.post(
    "/run",
    responses={
        401: {"description": "Session required to run a level or node that uses a hosted model."},
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
    token = request.cookies.get(PLAYER_SESSION_COOKIE)
    player = await container.players.lookup(token)
    if container.settings.APP_ENV == "production":
        await enforce_rate_limit(
            container.rate_limiter,
            "game_run_ip",
            client_address(request),
            limit=GAME_RUN_IP_LIMIT,
            window_seconds=GAME_RUN_IP_WINDOW,
        )
        if player.authenticated:
            await enforce_rate_limit(
                container.rate_limiter,
                "game_run_actor",
                _spend_owner(player, token),
                limit=GAME_RUN_ACTOR_LIMIT,
                window_seconds=GAME_RUN_ACTOR_WINDOW,
            )

    _reject_board_dataset(body.board)
    if len(body.board.nodes) > SAVE_MAX_NODES or len(body.board.edges) > SAVE_MAX_EDGES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"A board holds at most {SAVE_MAX_NODES} nodes and {SAVE_MAX_EDGES} wires.",
        )
    board = _to_engine_board(body.board)
    try:
        validate_board(board)
    except BoardValidationError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err

    uses_ai_nodes = any(node.kind in AI_AGENT_NODE_KINDS for node in board.nodes)

    jev_client = container.jev_client
    check_model = container.game_agent

    if body.level_id == "custom":
        if uses_ai_nodes and not player.ai_nodes_allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Sign in required to use AI agent nodes (safety_check, llm_review).",
            )
        return await _run_custom(body, board, player, container, token=token, jev_client=jev_client)

    level = get_level(body.level_id)
    if body.custom_message is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Campaign levels run the whole wave. Test single messages in the custom sandbox.",
        )
    uses_model_checks = any(node.kind in MODEL_CHECK_NODE_KINDS for node in board.nodes)
    counts_quota = level.agent is not None or uses_model_checks
    if counts_quota and not player.authenticated:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Start a session to play this level.",
        )
    if uses_ai_nodes and not player.ai_nodes_allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Sign in required to use AI agent nodes (safety_check, llm_review).",
        )
    if level.tier == "pro" and player.tier != "paid":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Upgrade to a Pro plan to play this campaign level.",
        )
    try:
        validate_board_for_level(board, level)
    except BoardValidationError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err

    ml_models, untrained_nodes = await _load_board_ml_models(board, token, player, container)

    is_custom_test = False
    spend_owner = _spend_owner(player, token)
    # A counted run holds its owner's lock from the budget check to the recorded spend,
    # so two runs of one player cannot both pass the budget (spec 0054).
    guard = container.spend_locks.hold(spend_owner) if counts_quota else nullcontext()
    async with guard:
        if counts_quota:
            try:
                await container.spend.ensure_within(spend_owner, player.tier)
            except SpendBudgetExceededError as err:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(err)) from err
            try:
                player = await container.players.reserve_run(token, is_custom_test=is_custom_test)
            except QuotaExceededError as err:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(err)) from err

        try:
            result = await run_wave(
                board,
                level_id=body.level_id,
                classifier=container.classifier,
                agent=(
                    None
                    if container.game_agent is None
                    else _cached(container.game_agent, container, level.id, "default")
                ),
                agents={
                    tier: _cached(model, container, level.id, tier)
                    for tier, model in container.game_agents.items()
                },
                canary_factory=lambda: level_canary(container.canary_seed, level.id),
                jev_client=jev_client,
                check_model=check_model,
                check_model_for=container.check_model_for,
                ml_models=ml_models,
                concurrency=WAVE_CONCURRENCY,
            )
        except BoardValidationError as err:
            if counts_quota:
                await container.players.release_run(token, is_custom_test=is_custom_test)
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err
        except AgentUnavailableError as err:
            if counts_quota:
                await container.players.release_run(token, is_custom_test=is_custom_test)
            cause = err.__cause__
            if isinstance(cause, ProviderAuthError):
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY, "The model provider rejected the API key."
                ) from None
            logger.exception("Game AI Agent model failed; run not counted")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "The AI Agent is unavailable right now. This run was not counted.",
            ) from err
        except BaseException:
            if counts_quota:
                await container.players.release_run(token, is_custom_test=is_custom_test)
            raise

        await container.spend.add(spend_owner, result.score.total_cost_usd)
    score_schema = WaveScoreSchema.model_validate(asdict(result.score))
    # Simulated agent runs are practice; live and model-free (Easy) runs are recorded.
    recordable = result.agent_mode in ("live", "none")
    if not is_custom_test and recordable:
        payload = ScoreCreateRequest(
            player_name=player.player_name,
            level_id=body.level_id,
            total_score=score_schema.total_score,
            medal=score_schema.medal,
            attacks_blocked=score_schema.attacks_protected,
            attacks_total=score_schema.attacks_total,
            false_alarms=score_schema.false_alarms,
            avg_latency_ms=score_schema.avg_latency_ms,
            total_cost_usd=score_schema.total_cost_usd,
            board=_strip_board_schema(body.board),
            won=score_schema.won,
            mastered=score_schema.follow_up_passed,
        )
        if player.can_record_scores:
            change = await container.scores.record_score_change(payload, email=player.email)
            await container.leaderboard.on_score_recorded(player.email, change)
        elif token and player.authenticated and player.is_anonymous:
            # Kept on the server until sign-in, never on the leaderboard (spec 0052).
            await container.anonymous_scores.record(
                owner_hash(token), payload, ttl=ANONYMOUS_SCORE_TTL
            )

    return GameRunResponse(
        level_id=result.level_id,
        traces=[_hidden_trace(MessageTraceSchema.model_validate(asdict(t))) for t in result.traces],
        score=score_schema,
        agent_mode=result.agent_mode,
        untrained_model_nodes=untrained_nodes,
        stop=RunStopSchema.model_validate(asdict(result.stop)) if result.stop else None,
    )


def _public_level(level: GameLevel) -> GameLevelSchema:
    """The level catalogue without prompt text or answers: wave prompts stay on the server."""
    schema = GameLevelSchema.model_validate(asdict(level))
    hidden = [
        m.model_copy(update={"text": "", "expected_tool": None, "forbidden_tools": []})
        for m in schema.messages
    ]
    return schema.model_copy(update={"messages": hidden})


def _spend_owner(player: PlayerSessionStatus, token: str | None) -> str:
    return player.email or owner_hash(token or "")


def _cached(
    model: UsageChatModel, container: Container, level_id: str, tier: str
) -> UsageChatModel:
    namespace = f"{level_id}:{tier}:{type(model).__name__}:{id(model)}"
    return CachedChatModel(model, container.agent_cache, namespace)


def _hidden_trace(trace: MessageTraceSchema) -> MessageTraceSchema:
    """Campaign prompts stay server secrets: no text, reply or free-text detail (API-FAIR-001)."""
    agent = trace.agent.model_copy(update={"reply": ""}) if trace.agent is not None else None
    return trace.model_copy(
        update={
            "text": "",
            "hops": [hop.model_copy(update={"detail": ""}) for hop in trace.hops],
            "agent": agent,
        }
    )


async def _run_custom(
    body: GameRunRequest,
    board: BoardGraph,
    player: PlayerSessionStatus,
    container: Container,
    *,
    token: str | None = None,
    jev_client: JevClient | None = None,
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

    ml_models, untrained_nodes = await _load_board_ml_models(board, token, player, container)
    model = container.byok_factory(custom.model.provider, custom.model.model, api_key)
    try:
        if body.custom_message is not None:
            result = await run_custom_message(
                board,
                profile=profile,
                message=body.custom_message,
                agent=model,
                classifier=container.classifier,
                jev_client=jev_client,
                check_model=model,
                check_model_for=lambda _: model,
                ml_models=ml_models,
            )
        else:
            result = await run_custom_wave(
                board,
                profile=profile,
                messages=messages,
                agent=model,
                classifier=container.classifier,
                jev_client=jev_client,
                check_model=model,
                check_model_for=lambda _: model,
                ml_models=ml_models,
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
        untrained_model_nodes=untrained_nodes,
    )


SAVE_MAX_BYTES = 256 * 1024
SAVE_MAX_NODES = 60
SAVE_MAX_EDGES = 200
SIGN_IN_TO_SAVE = "Sign in to save your board."


async def _saving_email(request: Request, container: Container, level_id: RunLevelId) -> str:
    """The signed-in player's email that keys the save; custom/pro need paid (spec 0023, 0039)."""
    player = await container.players.lookup(request.cookies.get(PLAYER_SESSION_COOKIE))
    if not player.authenticated or player.is_anonymous or not player.email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, SIGN_IN_TO_SAVE)
    if level_id == "custom" and player.tier != "paid":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Custom mode is for paid players.")
    if level_id != "custom" and get_level(level_id).tier == "pro" and player.tier != "paid":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Upgrade to a Pro plan to play or save this campaign level.",
        )
    return player.email


def _upgrade_legacy_save(save: dict[str, Any]) -> dict[str, Any]:
    """Migrate retired ``quick_screen`` nodes and strip ML training data from saved boards."""
    board = save.get("board")
    if not isinstance(board, dict):
        return save
    raw_nodes = board.get("nodes")
    if not isinstance(raw_nodes, list):
        return save
    changed = False
    upgraded_nodes: list[Any] = []
    for node in raw_nodes:
        if isinstance(node, dict) and node.get("kind") == "quick_screen":
            cfg = node.get("config")
            raw_cfg = cfg if isinstance(cfg, dict) else {}
            cleaned_cfg = {
                "algorithm": "tfidf",
                **{k: v for k, v in raw_cfg.items() if k not in ("model_id", "dataset")},
            }
            upgraded_nodes.append({**node, "kind": "ml_classifier", "config": cleaned_cfg})
            changed = True
        elif isinstance(node, dict) and node.get("kind") == "ml_classifier":
            cfg = node.get("config")
            if isinstance(cfg, dict) and ("model_id" in cfg or "dataset" in cfg):
                cleaned_cfg = {k: v for k, v in cfg.items() if k not in ("model_id", "dataset")}
                upgraded_nodes.append({**node, "config": cleaned_cfg})
                changed = True
            else:
                upgraded_nodes.append(node)
        else:
            upgraded_nodes.append(node)
    if not changed:
        return save
    return {**save, "board": {**board, "nodes": upgraded_nodes}}


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
    try:
        return SavedBoardResponse.model_validate(
            {**_upgrade_legacy_save(save), "level_id": level_id, "updated_at": updated_at}
        )
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No compatible board saved for this level."
        ) from exc


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
    save["board"] = _strip_board_schema(body.board).model_dump(mode="json")
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
    return await container.scores.list_scores(level_id=level_id, limit=limit)


@router.get("/leaderboard")
async def get_difficulty_leaderboard(
    response: Response,
    container: ContainerDep,
    difficulty: DifficultyCategory | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[DifficultyLeaderboardEntry]:
    """Return each player's aggregated scores across all levels in a difficulty category."""
    response.headers["Cache-Control"] = "public, s-maxage=10, stale-while-revalidate=30"
    return await container.leaderboard.get_leaderboard(difficulty=difficulty, limit=limit)


@router.get(
    "/leaderboard/me",
    responses={403: {"description": "Signed-in player session required."}},
)
async def get_my_leaderboard_rank(
    request: Request,
    response: Response,
    container: ContainerDep,
    difficulty: DifficultyCategory = "Easy",
) -> LeaderboardRankResponse:
    """Return the signed-in player's rank and score for one difficulty board."""
    player = await container.players.lookup(request.cookies.get(PLAYER_SESSION_COOKIE))
    if not player.authenticated or player.is_anonymous or not player.email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sign in to view your rank.")
    response.headers["Cache-Control"] = "private, no-store"
    return await container.leaderboard.get_player_rank(player.email, difficulty=difficulty)


@router.get("/progress")
async def get_player_progress(request: Request, container: ContainerDep) -> PlayerProgressResponse:
    """Return the authenticated player's per-level status and difficulty summaries."""
    token = request.cookies.get(PLAYER_SESSION_COOKIE)
    player = await container.players.lookup(token)
    if token and player.authenticated and player.is_anonymous:
        pending = await container.anonymous_scores.list_for(owner_hash(token))
        return build_player_progress([pending_score_record(row) for row in pending])
    if not player.authenticated or player.is_anonymous or not player.email:
        return build_player_progress([])
    owned = await container.scores.list_scores_for_owner(player.email)
    return build_player_progress(owned)


@router.delete(
    "/scores",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"description": "Admin access required."}},
)
async def clear_game_scores(
    request: Request, clearance: ClearanceDep, container: ContainerDep
) -> Response:
    """Clear scoreboard records. Requires an active admin clearance session."""
    client = client_address(request)
    if clearance is not Clearance.GRANTED:
        audit("scores.cleared", outcome="denied", client=client, warning=True)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin access required.")
    await container.scores.clear_scores()
    await container.leaderboard.on_scores_cleared()
    audit("scores.cleared", outcome="cleared", client=client)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _parse_train_input(body: GameTrainRequest) -> tuple[list[tuple[str, int]], int]:
    if body.algorithm not in ALLOWED_ML_ALGORITHMS:
        allowed_str = ", ".join(ALLOWED_ML_ALGORITHMS)
        raise BoardValidationError(
            f"Unsupported ML algorithm '{body.algorithm}'. Choose one of: {allowed_str}."
        )
    max_rows = 2000 if body.level_id == "custom" else 200
    if body.level_id not in (None, "custom"):
        # A level may limit how many rows the ML filter learns from (spec 0051).
        level_limit = get_level(body.level_id).constraints.max_training_rows
        if level_limit is not None:
            max_rows = min(max_rows, level_limit)
    if body.csv_text is not None:
        rows = parse_dataset_csv(body.csv_text, max_rows=max_rows)
    elif body.dataset is not None:
        rows = validate_training_rows(
            [{"text": row.text, "label": row.label} for row in body.dataset],
            max_rows=max_rows,
        )
    else:
        raise BoardValidationError("Provide CSV text or dataset rows to train.")
    return rows, max_rows


@router.post(
    "/train",
    responses={
        403: {"description": "Sign in required (paid plan for custom mode)."},
        413: {"description": "Training upload exceeds maximum size."},
        422: {"description": "Invalid algorithm, dataset, or oversized model."},
        429: {"description": "Daily or per-minute training limit reached."},
        503: {"description": "Training unavailable or timed out."},
    },
)
async def train_game_classifier(
    body: GameTrainRequest, request: Request, container: ContainerDep
) -> GameTrainResponse:
    """Validate, fit once, HMAC-sign, and store a temporary session ML model."""
    token = request.cookies.get(PLAYER_SESSION_COOKIE)
    player = await container.players.lookup(token)
    if not token or not player.authenticated or player.is_anonymous or not player.email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sign in to train the ML filter.")

    if body.level_id == "custom" and player.tier != "paid":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Custom mode is for paid players.")

    if body.level_id != "custom" and len(await request.body()) > CAMPAIGN_TRAIN_MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "Training upload exceeds the 128 KB campaign limit.",
        )

    signing_key = container.model_signing_key
    if signing_key is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Training is unavailable.")

    if container.settings.APP_ENV == "production":
        await enforce_rate_limit(
            container.rate_limiter,
            "game_train_email",
            player.email,
            limit=GAME_TRAIN_EMAIL_LIMIT,
            window_seconds=GAME_TRAIN_EMAIL_WINDOW,
        )

    try:
        rows, max_rows = _parse_train_input(body)
    except BoardValidationError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err

    try:
        await container.players.reserve_train(token)
    except QuotaExceededError as err:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(err)) from err

    model_id = secrets.token_urlsafe(16)
    use_subprocess = container.train_worker_cmd is not None or container.trainer is fit_classifier
    if use_subprocess:
        cmd = container.train_worker_cmd or (
            sys.executable,
            "-m",
            "shield_api.services.train_worker",
        )
        context = signing_context(owner_hash(token), model_id)
        try:
            algorithm, sample_count, accuracy, blob = await container.train_worker.run(
                cmd=cmd,
                algorithm=body.algorithm,
                rows=rows,
                max_rows=max_rows,
                signing_key=signing_key,
                context=context,
                timeout_seconds=container.train_timeout_seconds,
            )
        except TimeoutError:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Training took too long. Try a smaller dataset.",
            ) from None
        except BoardValidationError as err:
            await container.players.release_train(token)
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err
        except BaseException:
            await container.players.release_train(token)
            raise

        try:
            expires_at = await container.models.put_signed_blob(
                token,
                email=player.email,
                model_id=model_id,
                blob=blob,
            )
        except ModelTooLargeError as err:
            await container.players.release_train(token)
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err
        return GameTrainResponse(
            model_id=model_id,
            algorithm=algorithm,
            sample_count=sample_count,
            accuracy=accuracy,
            expires_at=expires_at,
        )

    try:
        fitted = await asyncio.wait_for(
            asyncio.to_thread(
                container.trainer, algorithm=body.algorithm, rows=rows, max_rows=max_rows
            ),
            timeout=container.train_timeout_seconds,
        )
    except TimeoutError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Training took too long. Try a smaller dataset.",
        ) from None
    except BoardValidationError as err:
        await container.players.release_train(token)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err
    except BaseException:
        await container.players.release_train(token)
        raise

    try:
        expires_at = await container.models.put(
            token,
            email=player.email,
            model_id=model_id,
            model=fitted.model,
            signing_key=signing_key,
        )
    except ModelTooLargeError as err:
        await container.players.release_train(token)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err

    return GameTrainResponse(
        model_id=model_id,
        algorithm=fitted.algorithm,
        sample_count=fitted.sample_count,
        accuracy=fitted.accuracy,
        expires_at=expires_at,
    )


@router.delete("/models", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session_models(request: Request, container: ContainerDep) -> Response:
    """Purge the current session's server-held ML models."""
    if token := request.cookies.get(PLAYER_SESSION_COOKIE):
        await container.models.purge_session(token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/models/purge", status_code=status.HTTP_204_NO_CONTENT)
async def purge_session_models_beacon(request: Request, container: ContainerDep) -> Response:
    """Beacon-compatible purge endpoint for pagehide cleanup."""
    if token := request.cookies.get(PLAYER_SESSION_COOKIE):
        await container.models.purge_session(token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
