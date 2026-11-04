"""Interfaces the engine depends on. Hosts supply the implementations.

Keeping these as structural ``Protocol``s means any object with the right
methods works: no inheritance, no registration, trivial test doubles.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from shield_engine.types import Adjudication, Clearance, DialogueTurn, ModerationResult, Signal


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


class ChatModel(Protocol):
    """Minimal async chat-completion interface over any LLM provider."""

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str: ...


class FeedbackStore(Protocol):
    """Human-reviewed labels keyed by exact prompt text (1 = malicious)."""

    def lookup(self, text: str) -> int | None: ...

    def record(self, text: str, label: int) -> None: ...


class Classifier(Protocol):
    """Layer 1: fast, local, synchronous scoring."""

    def score(self, text: str) -> Signal: ...


class Moderator(Protocol):
    """Optional independent safety check that can only escalate."""

    async def moderate(self, text: str) -> ModerationResult: ...


class Adjudicator(Protocol):
    """Layer 2: yields dialogue turns as they happen, then one Adjudication."""

    def adjudicate(
        self, prompt: str, clearance: Clearance
    ) -> AsyncIterator[DialogueTurn | Adjudication]: ...
