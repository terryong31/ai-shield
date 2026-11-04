"""Core value types shared by every layer of the engine.

Everything here is an immutable dataclass or a string enum so results can be
logged, compared in tests, and serialised by hosts without extra adapters.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Verdict(StrEnum):
    SAFE = "SAFE"
    UNCERTAIN = "UNCERTAIN"
    MALICIOUS = "MALICIOUS"


class ToolPolicy(StrEnum):
    ALLOW_ALL = "ALLOW_ALL"
    RESTRICTED = "RESTRICTED"
    SHUTDOWN = "SHUTDOWN"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Clearance(StrEnum):
    """What the host established about the caller's privileges.

    The engine never sees credentials; the host checks them and passes the
    outcome. ``DENIED`` means clearance was claimed but did not verify.
    """

    NONE = "NONE"
    DENIED = "DENIED"
    GRANTED = "GRANTED"


class DecisionLayer(StrEnum):
    """Which layer produced the final decision.

    Values match the identifiers already stored in existing audit logs.
    """

    CLASSIFIER = "LAYER_1_ML"
    ADJUDICATION = "LAYER_2_DUAL_AGENT"
    PASSTHROUGH = "SYSTEM"


class Stage(StrEnum):
    CLASSIFIER = "classifier"
    ADJUDICATION = "adjudication"


class Agent(StrEnum):
    ANALYST = "ANALYST"
    WARDEN = "WARDEN"


@dataclass(frozen=True, slots=True)
class Signal:
    """One detector's opinion about a prompt. ``score`` is P(malicious)."""

    detector: str
    verdict: Verdict
    score: float
    override: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModerationResult:
    flagged: bool
    categories: tuple[str, ...] = ()
    raw: str = ""
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DialogueTurn:
    agent: Agent
    message: str
    timestamp: float


@dataclass(frozen=True, slots=True)
class Adjudication:
    verdict: Verdict
    policy: ToolPolicy
    confidence: float
    summary: str
    analysis: str = ""
    dialogue: tuple[DialogueTurn, ...] = ()
    fallback: bool = False


@dataclass(frozen=True, slots=True)
class ScreeningContext:
    clearance: Clearance = Clearance.NONE


@dataclass(frozen=True, slots=True)
class Decision:
    verdict: Verdict
    policy: ToolPolicy
    blocked: bool
    layer: DecisionLayer
    reason: str
    classifier: Signal
    moderation: ModerationResult | None = None
    adjudication: Adjudication | None = None
