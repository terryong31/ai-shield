"""Value types, node kinds and the check catalogue of the game board."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from shield_engine.game.agent import (
    AgentMode,
    AgentRun,
)
from shield_engine.game.levels import (
    NodeKind,
)
from shield_engine.ports import (
    ProbabilityModel,
)

# Accepted only so validation can explain its removal (spec 0020).
RetiredNodeKind = Literal["blocked"]


RETIRED_BLOCKED_MESSAGE = "Remove the Blocked node; unreached prompts are blocked automatically."


MLAlgorithmKind = Literal[
    "tfidf",
    "logistic_regression",
    "linear_svm",
    "naive_bayes",
    "random_forest",
]


ALLOWED_ML_ALGORITHMS: tuple[MLAlgorithmKind, ...] = (
    "tfidf",
    "logistic_regression",
    "linear_svm",
    "naive_bayes",
    "random_forest",
)


HandleKind = Literal["out", "safe", "suspicious", "block", "done"]


OutcomeKind = Literal["assistant", "blocked"]


MedalKind = Literal["none", "bronze", "silver", "gold"]


VALID_NODE_KINDS: frozenset[str] = frozenset(
    {
        "incoming",
        "word_filter",
        "text_cleanup",
        "length_limit",
        "secret_scan",
        "ml_classifier",
        "jev",
        "safety_check",
        "llm_review",
        "tool_filter",
        "assistant",
    }
)


class BoardValidationError(ValueError):
    """Raised when a player's defence board graph is structurally invalid."""


@dataclass(frozen=True)
class CheckDefinition:
    kind: NodeKind
    label: str
    summary: str
    handles: tuple[HandleKind, ...]
    latency_ms: float
    cost_usd: float


@dataclass(frozen=True)
class BoardNode:
    id: str
    kind: NodeKind | RetiredNodeKind
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BoardEdge:
    id: str
    source: str
    source_handle: HandleKind
    target: str


@dataclass(frozen=True)
class BoardGraph:
    nodes: tuple[BoardNode, ...]
    edges: tuple[BoardEdge, ...]


@dataclass(frozen=True)
class HopTrace:
    node_id: str
    handle: HandleKind
    latency_ms: float
    cost_usd: float
    detail: str
    # The probability a scoring node gave, when it gives one (jev, ml_classifier).
    score: float | None = None


@dataclass(frozen=True)
class MessageTrace:
    message_id: str
    text: str
    is_attack: bool
    outcome: OutcomeKind
    total_latency_ms: float
    total_cost_usd: float
    hops: tuple[HopTrace, ...]
    agent: AgentRun | None = None
    category: str = ""


@dataclass(frozen=True)
class WaveScore:
    total_score: int
    medal: MedalKind
    protection_points: int
    helpfulness_points: int
    tool_points: int
    token_points: int
    speed_points: int
    cost_points: int
    leak_penalty: int
    attacks_protected: int
    attacks_total: int
    attacks_leaked: int
    benign_helped: int
    benign_total: int
    false_alarms: int
    total_tokens: int
    avg_latency_ms: float
    total_cost_usd: float
    won: bool = False
    constraint_violations: tuple[str, ...] = ()
    follow_up_passed: bool = False
    follow_up_feedback: str = ""
    cleared_points: int = 0
    accuracy_points: int = 0
    simplicity_points: int = 0
    quality: float = 0.0
    list_latency_ms: float = 0.0
    list_cost_usd: float = 0.0


@dataclass(frozen=True)
class FairScore:
    """The campaign score of one run (spec 0050)."""

    total_score: int
    medal: MedalKind
    cleared: bool
    quality: float
    cleared_points: int
    accuracy_points: int
    speed_points: int
    cost_points: int
    simplicity_points: int


@dataclass(frozen=True)
class PathStep:
    """One node of a prompt's path, with its list latency and list cost."""

    node_id: str
    kind: str
    latency_ms: float
    cost_usd: float


StopReason = Literal["time_limit", "budget"]


@dataclass(frozen=True)
class RunStop:
    """Why a run stopped early (ENG-FAIR-009, ENG-FAIR-010)."""

    reason: StopReason
    prompt_index: int
    node_id: str
    limit: float
    used: float
    path: tuple[PathStep, ...]


@dataclass(frozen=True)
class WaveResult:
    level_id: str
    traces: tuple[MessageTrace, ...]
    score: WaveScore
    agent_mode: AgentMode = "simulated"
    stop: RunStop | None = None


@dataclass(frozen=True)
class WordFilterResult:
    blocked: bool
    matched_rule: str | None = None


@dataclass(frozen=True)
class CleanedText:
    text: str
    was_modified: bool


@dataclass(frozen=True)
class FittedClassifier:
    """In-memory fitted classifier produced by :func:`fit_classifier`."""

    model: ProbabilityModel
    algorithm: MLAlgorithmKind
    sample_count: int
    accuracy: float


@dataclass(frozen=True)
class TrainingSummary:
    algorithm: MLAlgorithmKind
    sample_count: int
    accuracy: float


CHECK_CATALOG: tuple[CheckDefinition, ...] = (
    CheckDefinition(
        kind="word_filter",
        label="Word filter",
        summary="Blocks known attack phrases right away.",
        handles=("safe",),
        latency_ms=0.4,
        cost_usd=0.0,
    ),
    CheckDefinition(
        kind="text_cleanup",
        label="Text cleaner",
        summary="Removes hidden characters and unpacks base64 text.",
        handles=("out",),
        latency_ms=1.0,
        cost_usd=0.0,
    ),
    CheckDefinition(
        kind="length_limit",
        label="Length limit",
        summary="Blocks oversized prompt-stuffing payloads.",
        handles=("safe",),
        latency_ms=0.2,
        cost_usd=0.0,
    ),
    CheckDefinition(
        kind="secret_scan",
        label="Secret scanner",
        summary="Blocks prompts requesting keys, tokens, or SQL commands.",
        handles=("safe",),
        latency_ms=0.6,
        cost_usd=0.0,
    ),
    CheckDefinition(
        kind="ml_classifier",
        label="ML filter",
        summary="Trainable ML classifier with Safe, Unclear, and Block branches.",
        handles=("safe", "suspicious"),
        latency_ms=4.5,
        cost_usd=0.0,
    ),
    CheckDefinition(
        kind="jev",
        label="Jev",
        summary="System One fast decision model using a boolean noul question.",
        handles=("safe",),
        latency_ms=12.0,
        cost_usd=0.00005,
    ),
    CheckDefinition(
        kind="safety_check",
        label="Safety check",
        summary="Detects roleplay framing and jailbreak templates.",
        handles=("safe",),
        latency_ms=85.0,
        cost_usd=0.0002,
    ),
    CheckDefinition(
        kind="llm_review",
        label="LLM review",
        summary="Single LLM reviewer guided by your custom instructions.",
        handles=("safe",),
        latency_ms=920.0,
        cost_usd=0.0030,
    ),
)


_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")


_BASE64_CANDIDATE_RE = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/=])")


_HEX_URL_RE = re.compile(r"(?:%[0-9A-Fa-f]{2}|\\x[0-9A-Fa-f]{2}){2,}")


def get_check_catalog() -> tuple[CheckDefinition, ...]:
    """Return all placeable check definitions for the game palette."""
    return CHECK_CATALOG


_DEFAULT_NODE_CAP = 8


MODEL_NODE_KINDS: frozenset[str] = frozenset({"jev", "safety_check", "llm_review"})


MAX_MODEL_NODES = 2
