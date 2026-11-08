"""AI S.H.I.E.L.D. engine: a layered prompt-injection deflector.

Typical use::

    from shield_engine import Shield, ScreeningContext
    from shield_engine.models import load_baseline

    shield = Shield(load_baseline())
    decision = await shield.screen("ignore previous instructions", ScreeningContext())
    if decision.blocked:
        ...
"""

from importlib.metadata import PackageNotFoundError, version

from shield_engine.adjudication import DebateAdjudicator
from shield_engine.config import ShieldConfig
from shield_engine.detectors import ClassifierDetector, LlamaGuardModerator
from shield_engine.feedback import CsvFeedbackStore, InMemoryFeedbackStore
from shield_engine.pipeline import Shield
from shield_engine.policy import ToolSpec, allowed_tools
from shield_engine.ports import (
    ChatCompletion,
    ChatMessage,
    ChatModel,
    FeedbackStore,
    UsageChatModel,
)
from shield_engine.types import (
    Adjudication,
    Agent,
    Clearance,
    Decision,
    DecisionLayer,
    DialogueTurn,
    ModerationResult,
    RiskLevel,
    ScreeningContext,
    Signal,
    Stage,
    ToolPolicy,
    Verdict,
)

try:
    __version__ = version("shield-engine")
except PackageNotFoundError:  # pragma: no cover - running from a source checkout
    __version__ = "0.0.0+unknown"

__all__ = [
    "Adjudication",
    "Agent",
    "ChatCompletion",
    "ChatMessage",
    "ChatModel",
    "ClassifierDetector",
    "Clearance",
    "CsvFeedbackStore",
    "DebateAdjudicator",
    "Decision",
    "DecisionLayer",
    "DialogueTurn",
    "FeedbackStore",
    "InMemoryFeedbackStore",
    "LlamaGuardModerator",
    "ModerationResult",
    "RiskLevel",
    "ScreeningContext",
    "Shield",
    "ShieldConfig",
    "Signal",
    "Stage",
    "ToolPolicy",
    "ToolSpec",
    "UsageChatModel",
    "Verdict",
    "__version__",
    "allowed_tools",
]
