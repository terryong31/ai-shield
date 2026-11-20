"""Interfaces the engine depends on. Hosts supply the implementations.

Keeping these as structural ``Protocol``s means any object with the right
methods works: no inheritance, no registration, trivial test doubles.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from shield_engine.types import Signal


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


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    """A completion plus the token usage the provider reported (``None`` when it didn't)."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class UsageChatModel(Protocol):
    """A chat model that also reports token usage, used to score the game's AI Agent."""

    async def complete_with_usage(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatCompletion: ...


class Classifier(Protocol):
    """Fast, local, synchronous scoring (the game's ML filter)."""

    def score(self, text: str) -> Signal: ...


@dataclass(frozen=True, slots=True)
class JevEvaluation:
    """Result of evaluating a boolean ``noul`` question against TypeSafe's System One model."""

    probability: float
    input_tokens: int = 0
    output_tokens: int = 0


class JevClient(Protocol):
    """System One fast decision engine (TypeSafe Jev ``/v1/systemone``)."""

    async def evaluate_noul(
        self,
        state: str,
        question: str,
        *,
        model: str = "jev-latest",
    ) -> JevEvaluation: ...
