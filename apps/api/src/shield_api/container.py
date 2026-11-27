"""Composition root: the only place that knows which concrete adapters are wired in."""

import logging
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urlparse

from pydantic import SecretStr

from shield_api.providers.byok import build_byok_model
from shield_api.providers.typesafe import build_jev_client
from shield_api.services.admins import (
    AdminAuthenticator,
    SupabaseAdminAuthenticator,
)
from shield_api.services.agent_cache import AgentResultCache
from shield_api.services.anonymous_scores import (
    AnonymousScoreStore,
    InMemoryAnonymousScoreStore,
    SupabaseAnonymousScoreStore,
)
from shield_api.services.auth_flows import (
    AuthFlowStore,
    InMemoryAuthFlowStore,
    RedisAuthFlowStore,
)
from shield_api.services.billing import (
    LIVE_KEY_PREFIXES,
    TEST_KEY_PREFIXES,
    PaymentProvider,
    StripePayments,
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
from shield_api.services.spend import OwnerLocks, SpendLedger
from shield_api.services.train_worker import TrainWorkerRunner
from shield_api.settings import Settings
from shield_engine import UsageChatModel
from shield_engine.game import AgentTier, FittedClassifier, fit_classifier
from shield_engine.models import load_baseline
from shield_engine.ports import Classifier, JevClient

logger = logging.getLogger(__name__)


MIN_SIGNING_KEY_BYTES = 32


def resolve_model_signing_key(settings: Settings) -> bytes | None:
    if settings.MODEL_SIGNING_KEY and settings.MODEL_SIGNING_KEY.get_secret_value().strip():
        key = settings.MODEL_SIGNING_KEY.get_secret_value().encode("utf-8")
        if settings.APP_ENV == "production" and len(key) < MIN_SIGNING_KEY_BYTES:
            # A short key is guessable, so training stays off (spec 0054).
            logger.error("MODEL_SIGNING_KEY is shorter than 32 bytes; /game/train is disabled.")
            return None
        return key
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
    # Anonymous players' server-evaluated scores until they sign in (spec 0052).
    anonymous_scores: AnonymousScoreStore = field(default_factory=InMemoryAnonymousScoreStore)
    models: TrainedModelStore = field(default_factory=InMemoryTrainedModelStore)
    model_signing_key: bytes | None = field(default=None)
    train_timeout_seconds: float = TRAIN_TIMEOUT_SECONDS
    trainer: Callable[..., FittedClassifier] = fit_classifier
    train_worker_cmd: tuple[str, ...] | None = None
    train_worker: TrainWorkerRunner = field(default_factory=TrainWorkerRunner)
    attempts: AttemptLimiter = field(default_factory=AttemptLimiter)
    rate_limiter: RateLimiter = field(default_factory=RateLimiter)
    auth_flows: AuthFlowStore = field(default_factory=InMemoryAuthFlowStore)
    # Daily provider spend per player (spec 0050).
    spend: SpendLedger = field(default_factory=SpendLedger)
    # One run at a time per spend owner, so two runs cannot both pass the budget (spec 0054).
    spend_locks: OwnerLocks = field(default_factory=OwnerLocks)
    # Stored agent results and the seed of each level's fixed canary (spec 0050).
    agent_cache: AgentResultCache = field(default_factory=AgentResultCache)
    canary_seed: str = field(default_factory=lambda: secrets.token_hex(16))
    # The game's AI Agent model per tier (spec 0021). A tier missing here falls back to
    # ``game_agent``, and with neither the level runs the offline stand-in.
    game_agents: dict[AgentTier, UsageChatModel] = field(default_factory=dict)
    game_agent: UsageChatModel | None = None
    jev_client: JevClient | None = None
    # Stripe checkout (spec 0049); None means billing is off.
    payments: PaymentProvider | None = None
    # Builds the player's own model for one custom run (spec 0022); tests swap in a fake.
    byok_factory: Callable[[str, str, str], UsageChatModel] = build_byok_model
    jev_factory: Callable[[str], JevClient] = build_jev_client

    def __post_init__(self) -> None:
        if getattr(self, "leaderboard", None) is None:
            self.leaderboard = LeaderboardService(self.scores)
        if self.model_signing_key is None:
            self.model_signing_key = resolve_model_signing_key(self.settings)

    def check_model_for(self, model_name: str) -> UsageChatModel | None:
        return check_model_for(self.settings, self.game_agent, self.game_agents, model_name)


def check_model_for(
    settings: Settings,
    game_agent: UsageChatModel | None,
    game_agents: Mapping[AgentTier, UsageChatModel],
    model_name: str,
) -> UsageChatModel | None:
    """The model that runs a review check node named ``model_name``."""
    if game_agent is not None:
        return game_agent
    lowered = model_name.lower()
    if lowered.startswith(("gemini", "gemma")) and settings.GOOGLE_API_KEY is not None:
        from shield_api.providers.gemini import GeminiChatModel

        return GeminiChatModel(settings.GOOGLE_API_KEY.get_secret_value(), model_name)
    if settings.GROQ_API_KEY is not None and lowered.startswith(
        ("openai/gpt-oss", "qwen/", "meta-llama/")
    ):
        from shield_engine.adapters.groq import GroqChatModel

        return GroqChatModel(settings.GROQ_API_KEY.get_secret_value(), model_name)
    return game_agents.get("standard") or game_agents.get("budget")


def build_game_models(
    settings: Settings,
) -> tuple[dict[AgentTier, UsageChatModel], JevClient | None]:
    """The agent model of each tier and the Jev client, from the configured keys."""
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
    return game_agents, jev_client


def _secret(value: SecretStr | None) -> str:
    return value.get_secret_value().strip() if value else ""


def build_container(settings: Settings) -> Container:
    missing: list[str] = []
    # Production refuses settings that weaken transport or sessions (spec 0054).
    insecure: list[str] = []
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
        redis_url = _secret(settings.REDIS_URL)
        if redis_url and not redis_url.startswith("rediss://"):
            insecure.append("REDIS_URL must use rediss://")
        if not settings.SESSION_COOKIE_SECURE:
            insecure.append("SESSION_COOKIE_SECURE must be true")
        if settings.ALLOW_SELF_UPGRADE:
            insecure.append("ALLOW_SELF_UPGRADE must be false")
        parsed_web = urlparse(settings.WEB_BASE_URL.strip())
        if parsed_web.scheme != "https":
            insecure.append("WEB_BASE_URL must use https://")
        if (
            parsed_web.scheme not in {"http", "https"}
            or not parsed_web.hostname
            or parsed_web.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
        ):
            missing.append("WEB_BASE_URL")
    stripe_key = _secret(settings.STRIPE_SECRET_KEY)
    stripe_webhook = _secret(settings.STRIPE_WEBHOOK_SECRET)
    if stripe_key:
        if not stripe_key.startswith(TEST_KEY_PREFIXES + LIVE_KEY_PREFIXES):
            missing.append("STRIPE_SECRET_KEY")
        if not stripe_webhook:
            missing.append("STRIPE_WEBHOOK_SECRET")
    if missing:
        names = ", ".join(missing)
        msg = (
            f"Missing required configuration: {names}. "
            "Start local Supabase with `mise run db:start` or set them in apps/api/.env."
        )
        logger.error(msg)
        raise ConfigurationError(msg)
    if insecure:
        msg = "Insecure production configuration: " + "; ".join(insecure) + "."
        logger.error(msg)
        raise ConfigurationError(msg)

    game_agents, jev_client = build_game_models(settings)

    from supabase import create_client

    assert settings.SUPABASE_KEY is not None
    url, key = settings.SUPABASE_URL.strip(), settings.SUPABASE_KEY.get_secret_value().strip()
    client = create_client(url, key)
    scores: ScoreStore = SupabaseScoreStore(client)
    sessions: SessionStore = SupabaseSessionStore(client)
    players: PlayerStore = SupabasePlayerStore(client)
    admins: AdminAuthenticator = SupabaseAdminAuthenticator(lambda: create_client(url, key))
    web_base = settings.WEB_BASE_URL.strip().rstrip("/")
    identity: PlayerIdentity = SupabasePlayerIdentity(
        lambda: create_client(url, key), redirect_to=f"{web_base}/auth/confirmed"
    )

    leaderboard = LeaderboardService(scores)
    models: TrainedModelStore = InMemoryTrainedModelStore()
    rate_limiter = RateLimiter()
    auth_flows: AuthFlowStore = InMemoryAuthFlowStore()
    spend = SpendLedger()
    if settings.REDIS_URL and settings.REDIS_URL.get_secret_value().strip():
        try:
            import redis.asyncio as aioredis

            # No client name or version: a new connection then skips CLIENT SETINFO and
            # the package metadata read, a blocking file read on every new connection.
            redis_client = aioredis.from_url(
                settings.REDIS_URL.get_secret_value(),
                decode_responses=True,
                lib_name=None,
                lib_version=None,
            )
            leaderboard = LeaderboardService(scores, redis_client)
            models = RedisTrainedModelStore(redis_client)
            rate_limiter = RateLimiter(redis_client=redis_client)
            auth_flows = RedisAuthFlowStore(redis_client)
            spend = SpendLedger(redis_client=redis_client)
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
        anonymous_scores=SupabaseAnonymousScoreStore(client),
        models=models,
        model_signing_key=resolve_model_signing_key(settings),
        admins=admins,
        identity=identity,
        game_agents=game_agents,
        jev_client=jev_client,
        payments=StripePayments(stripe_key, stripe_webhook) if stripe_key else None,
        attempts=AttemptLimiter(
            max_attempts=settings.CLEARANCE_MAX_ATTEMPTS,
            window=timedelta(minutes=settings.CLEARANCE_WINDOW_MINUTES),
        ),
        rate_limiter=rate_limiter,
        auth_flows=auth_flows,
        spend=spend,
    )
