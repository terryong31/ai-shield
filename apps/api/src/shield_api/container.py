"""Composition root: the only place that knows which concrete adapters are wired in."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

from shield_api.providers.byok import build_byok_model
from shield_api.providers.typesafe import build_jev_client
from shield_api.services.admins import (
    AdminAuthenticator,
    NoAdminAuthenticator,
    SupabaseAdminAuthenticator,
)
from shield_api.services.identity import PlayerIdentity, SupabasePlayerIdentity
from shield_api.services.players import (
    InMemoryPlayerStore,
    PlayerStore,
    SqlitePlayerStore,
    SupabasePlayerStore,
)
from shield_api.services.scores import (
    InMemoryNotifier,
    LeaderboardNotifier,
    RedisCachedScoreStore,
    RedisPubSubNotifier,
    ScoreStore,
    SqliteScoreStore,
    SupabaseScoreStore,
)
from shield_api.services.sessions import (
    AttemptLimiter,
    InMemorySessionStore,
    SessionStore,
    SqliteSessionStore,
    SupabaseSessionStore,
)
from shield_api.settings import Settings
from shield_engine import UsageChatModel
from shield_engine.game import AgentTier
from shield_engine.models import load_baseline
from shield_engine.ports import Classifier, JevClient

logger = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    # The game's ML filter baseline.
    classifier: Classifier
    # Leaderboard scores (game.scores).
    scores: ScoreStore
    leaderboard_notifier: LeaderboardNotifier = field(default_factory=InMemoryNotifier)
    sessions: SessionStore = field(default_factory=InMemorySessionStore)
    players: PlayerStore = field(default_factory=InMemoryPlayerStore)
    attempts: AttemptLimiter = field(default_factory=AttemptLimiter)
    # Who may hold admin clearance: Supabase users with app_metadata.role "admin".
    admins: AdminAuthenticator = field(default_factory=NoAdminAuthenticator)
    # Supabase Auth owns player passwords and email confirmation (spec 0027);
    # None means local development accounts with immediate sign-in.
    identity: PlayerIdentity | None = None
    # The game's AI Agent model per tier (spec 0021). A tier missing here falls back to
    # ``game_agent``, and with neither the level runs the offline stand-in.
    game_agents: dict[AgentTier, UsageChatModel] = field(default_factory=dict)
    game_agent: UsageChatModel | None = None
    jev_client: JevClient | None = None
    # Builds the player's own model for one custom run (spec 0022); tests swap in a fake.
    byok_factory: Callable[[str, str, str], UsageChatModel] = build_byok_model
    jev_factory: Callable[[str], JevClient] = build_jev_client

    def check_model_for(self, model_name: str) -> UsageChatModel | None:
        if self.game_agent is not None:
            return self.game_agent
        lowered = model_name.lower()
        if (lowered.startswith("gemini") or "shieldgemma" in lowered) and (
            self.settings.GOOGLE_API_KEY is not None
        ):
            from shield_api.providers.gemini import GeminiChatModel

            return GeminiChatModel(self.settings.GOOGLE_API_KEY.get_secret_value(), model_name)
        if self.settings.GROQ_API_KEY is not None and any(
            k in lowered for k in ("llama", "guard", "qwen", "nemotron")
        ):
            from shield_engine.adapters.groq import GroqChatModel

            return GroqChatModel(self.settings.GROQ_API_KEY.get_secret_value(), model_name)
        return self.game_agents.get("standard") or self.game_agents.get("budget")


def build_container(settings: Settings) -> Container:
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

    # Every domain (audit, game, players) persists in Supabase when it is configured,
    # otherwise in SQLite domain databases beside SQLITE_PATH (spec 0024).
    scores: ScoreStore
    sessions: SessionStore
    players: PlayerStore
    admins: AdminAuthenticator = NoAdminAuthenticator()
    identity: PlayerIdentity | None = None
    if settings.SUPABASE_URL and settings.SUPABASE_KEY:
        from supabase import create_client

        url, key = settings.SUPABASE_URL, settings.SUPABASE_KEY.get_secret_value()
        client = create_client(url, key)
        scores = SupabaseScoreStore(client)
        sessions = SupabaseSessionStore(client)
        players = SupabasePlayerStore(client)
        admins = SupabaseAdminAuthenticator(lambda: create_client(url, key))
        identity = SupabasePlayerIdentity(
            lambda: create_client(url, key), redirect_to=f"{settings.WEB_BASE_URL}/auth/confirmed"
        )
    else:
        logger.info("Supabase not configured: data stored in SQLite at %s", settings.SQLITE_PATH)
        scores = SqliteScoreStore(settings.SQLITE_PATH)
        sessions = SqliteSessionStore(settings.SQLITE_PATH)
        players = SqlitePlayerStore(settings.SQLITE_PATH)

    leaderboard_notifier: LeaderboardNotifier = InMemoryNotifier()
    if settings.REDIS_URL:
        try:
            import redis.asyncio as aioredis

            redis_client = aioredis.from_url(
                settings.REDIS_URL.get_secret_value(), decode_responses=True
            )
            leaderboard_notifier = RedisPubSubNotifier(redis_client)
            scores = RedisCachedScoreStore(scores, redis_client, notifier=leaderboard_notifier)
            logger.info("Redis leaderboard cache enabled")
        except Exception as exc:
            logger.warning("Redis unavailable; falling back to %s: %s", scores.backend, exc)

    return Container(
        settings=settings,
        classifier=load_baseline(),
        scores=scores,
        leaderboard_notifier=leaderboard_notifier,
        sessions=sessions,
        players=players,
        admins=admins,
        identity=identity,
        game_agents=game_agents,
        jev_client=jev_client,
        attempts=AttemptLimiter(
            max_attempts=settings.CLEARANCE_MAX_ATTEMPTS,
            window=timedelta(minutes=settings.CLEARANCE_WINDOW_MINUTES),
        ),
    )
