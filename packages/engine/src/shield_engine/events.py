"""Events emitted by :meth:`shield_engine.Shield.screen_stream`.

Hosts translate these into whatever transport they use (NDJSON, SSE,
websockets, logs). The stream always ends with exactly one ``DecisionMade``.
"""

from __future__ import annotations

from dataclasses import dataclass

from shield_engine.types import Decision, DialogueTurn, ModerationResult, Signal, Stage


@dataclass(frozen=True, slots=True)
class StageStarted:
    stage: Stage


@dataclass(frozen=True, slots=True)
class ClassifierScored:
    signal: Signal


@dataclass(frozen=True, slots=True)
class ModerationFlagged:
    result: ModerationResult


@dataclass(frozen=True, slots=True)
class DebateTurn:
    turn: DialogueTurn


@dataclass(frozen=True, slots=True)
class DecisionMade:
    decision: Decision


type ShieldEvent = StageStarted | ClassifierScored | ModerationFlagged | DebateTurn | DecisionMade
