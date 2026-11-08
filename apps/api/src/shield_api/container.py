"""Composition root: the only place that knows which concrete adapters are wired in."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol

from shield_api.demo.assistant import Assistant, DemoAssistant
from shield_api.demo.byok import build_byok_model
from shield_api.services.audit import AuditLog, SqliteAuditLog, SupabaseAuditLog
from shield_api.services.players import (
    InMemoryPlayerStore,
    PlayerStore,
    SqlitePlayerStore,
    SupabasePlayerStore,
)
from shield_api.services.sessions import (
    AttemptLimiter,
    InMemorySessionStore,
    SessionStore,
    SqliteSessionStore,
    SupabaseSessionStore,
)
from shield_api.settings import Settings
from shield_engine import (
    ChatModel,
    CsvFeedbackStore,
    DebateAdjudicator,
    LlamaGuardModerator,
    Shield,
    Signal,
    UsageChatModel,
)
from shield_engine.game import AgentTier
from shield_engine.models import load_baseline

logger = logging.getLogger(__name__)


class LearningClassifier(Protocol):
    def score(self, text: str) -> Signal: ...

    def learn(self, text: str, label: int) -> None: ...


@dataclass
class Container:
    settings: Settings
    classifier: LearningClassifier
    shield: Shield
    audit_log: AuditLog
    assistant: Assistant
    sessions: SessionStore = field(default_factory=InMemorySessionStore)
    players: PlayerStore = field(default_factory=InMemoryPlayerStore)
    attempts: AttemptLimiter = field(default_factory=AttemptLimiter)
    # The game's AI Agent model per tier (spec 0021). A tier missing here falls back to
    # ``game_agent``, and with neither the level runs the offline stand-in.
    game_agents: dict[AgentTier, UsageChatModel] = field(default_factory=dict)
    game_agent: UsageChatModel | None = None
    # Builds the player's own model for one custom run (spec 0022); tests swap in a fake.
    byok_factory: Callable[[str, str, str], UsageChatModel] = build_byok_model


def build_container(settings: Settings) -> Container:
    classifier = load_baseline(feedback=CsvFeedbackStore(settings.FEEDBACK_PATH))

    moderator = adjudicator = None
    chat_models: list[ChatModel] = []
    game_agents: dict[AgentTier, UsageChatModel] = {}

    if settings.GOOGLE_API_KEY:
        from shield_api.demo.gemini import GeminiChatModel

        google_key = settings.GOOGLE_API_KEY.get_secret_value()
        gemini = GeminiChatModel(google_key, settings.GEMINI_MODEL)
        chat_models.append(gemini)
        standard_model = settings.GAME_MODEL_STANDARD or settings.GEMINI_MODEL
        game_agents["standard"] = (
            gemini
            if standard_model == settings.GEMINI_MODEL
            else GeminiChatModel(google_key, standard_model)
        )

    if settings.GROQ_API_KEY:
        from shield_engine.adapters.groq import GroqChatModel

        key = settings.GROQ_API_KEY.get_secret_value()
        moderator = LlamaGuardModerator(GroqChatModel(key, settings.GROQ_GUARD_MODEL))
        adjudicator = DebateAdjudicator(GroqChatModel(key, settings.GROQ_DEBATE_MODEL))
        groq_chat = GroqChatModel(key, settings.GROQ_CHAT_MODEL)
        chat_models.append(groq_chat)
        if "standard" not in game_agents:
            game_agents["standard"] = GroqChatModel(
                key, settings.GAME_MODEL_STANDARD or settings.GROQ_CHAT_MODEL
            )
        game_agents["budget"] = GroqChatModel(key, settings.GAME_MODEL_BUDGET)
    else:
        logger.warning("GROQ_API_KEY not set: moderation and debate are disabled")

    # Every domain (audit, game, players) persists in Supabase when it is configured,
    # otherwise in SQLite domain databases beside SQLITE_PATH (spec 0024).
    audit_log: AuditLog
    sessions: SessionStore
    players: PlayerStore
    if settings.SUPABASE_URL and settings.SUPABASE_KEY:
        from supabase import create_client

        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY.get_secret_value())
        audit_log = SupabaseAuditLog(client)
        sessions = SupabaseSessionStore(client)
        players = SupabasePlayerStore(client)
    else:
        logger.info("Supabase not configured: data stored in SQLite at %s", settings.SQLITE_PATH)
        audit_log = SqliteAuditLog(settings.SQLITE_PATH)
        sessions = SqliteSessionStore(settings.SQLITE_PATH)
        players = SqlitePlayerStore(settings.SQLITE_PATH)

    return Container(
        settings=settings,
        classifier=classifier,
        shield=Shield(classifier, moderator=moderator, adjudicator=adjudicator),
        audit_log=audit_log,
        assistant=DemoAssistant(chat_models),
        sessions=sessions,
        players=players,
        game_agents=game_agents,
        attempts=AttemptLimiter(
            max_attempts=settings.CLEARANCE_MAX_ATTEMPTS,
            window=timedelta(minutes=settings.CLEARANCE_WINDOW_MINUTES),
        ),
    )
