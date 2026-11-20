"""Core value types shared by the engine's checks.

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


@dataclass(frozen=True, slots=True)
class Signal:
    """One detector's opinion about a prompt. ``score`` is P(malicious)."""

    detector: str
    verdict: Verdict
    score: float
    override: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)
