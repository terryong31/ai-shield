"""Composition root: the only place that knows which concrete adapters are wired in."""

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

from shield_api.providers.byok import build_byok_model
from shield_api.providers.typesafe import build_jev_client
from shield_api.services.admins import (
    AdminAuthenticator,
    SupabaseAdminAuthenticator,
)
from shield_api.services.identity import PlayerIdentity, SupabasePlayerIdentity
from shield_api.services.leaderboard import LeaderboardService
from shield_api.services.models import (
    TRAIN_TIMEOUT_SECONDS,
    InMemoryTrainedModelStore,
    RedisTrainedModelStore,
    TrainedModelStore,
)
from shield_api.services.players import (
    InMemoryPlayerStore,
    PlayerStore,
    SupabasePlayerStore,
)
from shield_api.services.rate_limit import RateLimiter
from shield_api.services.scores import (
    ScoreStore,
    SupabaseScoreStore,
)
from shield_api.services.sessions import (
    AttemptLimiter,
    InMemorySessionStore,
    SessionStore,
    SupabaseSessionStore,
)
from shield_api.services.train_worker import TrainWorkerRunner
from shield_api.settings import Settings
from shield_engine import UsageChatModel
from shield_engine.game import AgentTier, FittedClassifier, fit_classifier
from shield_engine.models import load_baseline
from shield_engine.ports import Classifier, JevClient

logger = logging.getLogger(__name__)


def resolve_model_signing_key(settings: Settings) -> bytes | None:
    if settings.MODEL_SIGNING_KEY and settings.MODEL_SIGNING_KEY.get_secret_value().strip():
        return settings.MODEL_SIGNING_KEY.get_secret_value().encode("utf-8")
    if settings.APP_ENV == "development":
        return secrets.token_bytes(32)
    return None


class ConfigurationError(RuntimeError):
    """Raised when required gateway configuration is missing or invalid."""


@dataclass
class Container:
    settings: Settings
    # The game's ML filter baseline.
    classifier: Classifier
    # Leaderboard scores (game.scores).
    scores: ScoreStore
    # Who may hold admin clearance: Supabase users with app_metadata.role "admin".
    admins: AdminAuthenticator
    # Supabase Auth owns player passwords and email confirmation (spec 0027, 0046).
    identity: PlayerIdentity
    leaderboard: LeaderboardService = field(default=None)  # type: ignore[assignment]
    sessions: SessionStore = field(default_factory=InMemorySessionStore)
    players: PlayerStore = field(default_factory=InMemoryPlayerStore)
    models: TrainedModelStore = field(default_factory=InMemoryTrainedModelStore)
    model_signing_key: bytes | None = field(default=None)
    train_timeout_seconds: float = TRAIN_TIMEOUT_SECONDS
    trainer: Callable[..., FittedClassifier] = fit_classifier
    train_worker_cmd: tuple[str, ...] | None = None
    train_worker: TrainWorkerRunner = field(default_factory=TrainWorkerRunner)
    attempts: AttemptLimiter = field(default_factory=AttemptLimiter)
    rate_limiter: RateLimiter = field(default_factory=RateLimiter)
    # The game's AI Agent model per tier (spec 0021). A tier missing here falls back to
    # ``game_agent``, and with neither the level runs the offline stand-in.
    game_agents: dict[AgentTier, UsageChatModel] = field(default_factory=dict)
    game_agent: UsageChatModel | None = None
    jev_client: JevClient | None = None
    # Builds the player's own model for one custom run (spec 0022); tests swap in a fake.
    byok_factory: Callable[[str, str, str], UsageChatModel] = build_byok_model
    jev_factory: Callable[[str], JevClient] = build_jev_client

    def __post_init__(self) -> None:
        if getattr(self, "leaderboard", None) is None:
            self.leaderboard = LeaderboardService(self.scores)
        if self.model_signing_key is None:
            self.model_signing_key = resolve_model_signing_key(self.settings)

    def check_model_for(self, model_name: str) -> UsageChatModel | None:
        if self.game_agent is not None:
            return self.game_agent
        lowered = model_name.lower()
        if lowered.startswith(("gemini", "gemma")) and self.settings.GOOGLE_API_KEY is not None:
            from shield_api.providers.gemini import GeminiChatModel

            return GeminiChatModel(self.settings.GOOGLE_API_KEY.get_secret_value(), model_name)
        if self.settings.GROQ_API_KEY is not None and lowered.startswith(
            ("openai/gpt-oss", "qwen/", "meta-llama/")
        ):
            from shield_engine.adapters.groq import GroqChatModel

            return GroqChatModel(self.settings.GROQ_API_KEY.get_secret_value(), model_name)
        return self.game_agents.get("standard") or self.game_agents.get("budget")


def build_container(settings: Settings) -> Container:
    missing: list[str] = []
    if not settings.SUPABASE_URL.strip():
        missing.append("SUPABASE_URL")
    if not (settings.SUPABASE_KEY and settings.SUPABASE_KEY.get_secret_value().strip()):
        missing.append("SUPABASE_KEY")
    if settings.APP_ENV == "production":
        if not (settings.REDIS_URL and settings.REDIS_URL.get_secret_value().strip()):
            missing.append("REDIS_URL")
        if not (settings.TRUSTED_CLIENT_IP_HEADER and settings.TRUSTED_CLIENT_IP_HEADER.strip()):
            missing.append("TRUSTED_CLIENT_IP_HEADER")
        if not (
            settings.TRUSTED_PROXY_SECRET
            and settings.TRUSTED_PROXY_SECRET.get_secret_value().strip()
        ):
            missing.append("TRUSTED_PROXY_SECRET")
    if missing:
        names = ", ".join(missing)
        msg = (
            f"Missing required configuration: {names}. "
            "Start local Supabase with `mise run db:start` or set them in apps/api/.env."
        )
        logger.error(msg)
        raise ConfigurationError(msg)

    game_agents: dict[AgentTier, UsageChatModel] = {}

    if settings.GOOGLE_API_KEY:
        from shield_api.providers.gemini import GeminiChatModel

        game_agents["standard"] = GeminiChatModel(
            settings.GOOGLE_API_KEY.get_secret_value(),
            settings.GAME_MODEL_STANDARD or settings.GEMINI_MODEL,
        )

    if settings.GROQ_API_KEY:
        from shield_engine.adapters.groq import GroqChatModel

        key = settings.GROQ_API_KEY.get_secret_value()
        if "standard" not in game_agents:
            game_agents["standard"] = GroqChatModel(
                key, settings.GAME_MODEL_STANDARD or settings.GROQ_CHAT_MODEL
            )
        game_agents["budget"] = GroqChatModel(key, settings.GAME_MODEL_BUDGET)

    if not game_agents:
        logger.warning("No GOOGLE_API_KEY or GROQ_API_KEY: agent levels run the offline stand-in")

    jev_client: JevClient | None = None
    if settings.TYPESAFE_API_KEY:
        jev_client = build_jev_client(settings.TYPESAFE_API_KEY.get_secret_value())

    from supabase import create_client

    assert settings.SUPABASE_KEY is not None
    url, key = settings.SUPABASE_URL.strip(), settings.SUPABASE_KEY.get_secret_value().strip()
    client = create_client(url, key)
    scores: ScoreStore = SupabaseScoreStore(client)
    sessions: SessionStore = SupabaseSessionStore(client)
    players: PlayerStore = SupabasePlayerStore(client)
    admins: AdminAuthenticator = SupabaseAdminAuthenticator(lambda: create_client(url, key))
    identity: PlayerIdentity = SupabasePlayerIdentity(
        lambda: create_client(url, key), redirect_to=f"{settings.WEB_BASE_URL}/auth/confirmed"
    )

    leaderboard = LeaderboardService(scores)
    models: TrainedModelStore = InMemoryTrainedModelStore()
    rate_limiter = RateLimiter()
    if settings.REDIS_URL and settings.REDIS_URL.get_secret_value().strip():
        try:
            import redis.asyncio as aioredis

            redis_client = aioredis.from_url(
                settings.REDIS_URL.get_secret_value(), decode_responses=True
            )
            leaderboard = LeaderboardService(scores, redis_client)
            models = RedisTrainedModelStore(redis_client)
            rate_limiter = RateLimiter(redis_client=redis_client)
            logger.info("Redis leaderboard service and rate limiter enabled")
        except Exception as exc:
            logger.warning("Redis unavailable; falling back to %s: %s", scores.backend, exc)

    return Container(
        settings=settings,
        classifier=load_baseline(),
        scores=scores,
        leaderboard=leaderboard,
        sessions=sessions,
        players=players,
        models=models,
        model_signing_key=resolve_model_signing_key(settings),
        admins=admins,
        identity=identity,
        game_agents=game_agents,
        jev_client=jev_client,
        attempts=AttemptLimiter(
            max_attempts=settings.CLEARANCE_MAX_ATTEMPTS,
            window=timedelta(minutes=settings.CLEARANCE_WINDOW_MINUTES),
        ),
        rate_limiter=rate_limiter,
    )
