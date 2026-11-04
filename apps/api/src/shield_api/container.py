"""Composition root: the only place that knows which concrete adapters are wired in."""

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol

from shield_api.demo.assistant import Assistant, DemoAssistant
from shield_api.services.audit import AuditLog, SqliteAuditLog, SupabaseAuditLog
from shield_api.services.sessions import (
    AttemptLimiter,
    InMemorySessionStore,
    SessionStore,
    SqliteSessionStore,
)
from shield_api.settings import Settings
from shield_engine import (
    ChatModel,
    CsvFeedbackStore,
    DebateAdjudicator,
    LlamaGuardModerator,
    Shield,
    Signal,
)
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
    attempts: AttemptLimiter = field(default_factory=AttemptLimiter)


def build_container(settings: Settings) -> Container:
    classifier = load_baseline(feedback=CsvFeedbackStore(settings.FEEDBACK_PATH))

    moderator = adjudicator = None
    chat_models: list[ChatModel] = []

    if settings.GOOGLE_API_KEY:
        from shield_api.demo.gemini import GeminiChatModel

        chat_models.append(
            GeminiChatModel(settings.GOOGLE_API_KEY.get_secret_value(), settings.GEMINI_MODEL)
        )

    if settings.GROQ_API_KEY:
        from shield_engine.adapters.groq import GroqChatModel

        key = settings.GROQ_API_KEY.get_secret_value()
        moderator = LlamaGuardModerator(GroqChatModel(key, settings.GROQ_GUARD_MODEL))
        adjudicator = DebateAdjudicator(GroqChatModel(key, settings.GROQ_DEBATE_MODEL))
        chat_models.append(GroqChatModel(key, settings.GROQ_CHAT_MODEL))
    else:
        logger.warning("GROQ_API_KEY not set: moderation and debate are disabled")

    audit_log: AuditLog
    if settings.SUPABASE_URL and settings.SUPABASE_KEY:
        from supabase import create_client

        audit_log = SupabaseAuditLog(
            create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY.get_secret_value())
        )
    else:
        logger.info("Supabase not configured: audit log stored in %s", settings.SQLITE_PATH)
        audit_log = SqliteAuditLog(settings.SQLITE_PATH)

    return Container(
        settings=settings,
        classifier=classifier,
        shield=Shield(classifier, moderator=moderator, adjudicator=adjudicator),
        audit_log=audit_log,
        assistant=DemoAssistant(chat_models),
        sessions=SqliteSessionStore(settings.SQLITE_PATH),
        attempts=AttemptLimiter(
            max_attempts=settings.CLEARANCE_MAX_ATTEMPTS,
            window=timedelta(minutes=settings.CLEARANCE_WINDOW_MINUTES),
        ),
    )
