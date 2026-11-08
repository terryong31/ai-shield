"""Deterministic test doubles for the engine's ports.

Shipped with the package so that host applications can test their
integration without network access or trained models.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from shield_engine.ports import ChatCompletion, ChatMessage
from shield_engine.types import (
    Adjudication,
    Agent,
    Clearance,
    DialogueTurn,
    ModerationResult,
    Signal,
    ToolPolicy,
    Verdict,
)


@dataclass
class StaticClassifier:
    verdict: Verdict = Verdict.SAFE
    probability: float = 0.05
    calls: list[str] = field(default_factory=list)
    learned: list[tuple[str, int]] = field(default_factory=list)

    def score(self, text: str) -> Signal:
        self.calls.append(text)
        return Signal(detector="classifier", verdict=self.verdict, score=self.probability)

    def learn(self, text: str, label: int) -> None:
        self.learned.append((text, label))


@dataclass
class StaticModerator:
    result: ModerationResult = field(default_factory=lambda: ModerationResult(flagged=False))
    calls: list[str] = field(default_factory=list)

    async def moderate(self, text: str) -> ModerationResult:
        self.calls.append(text)
        return self.result


@dataclass
class ScriptedAdjudicator:
    """Yields ``turns`` then a fixed adjudication, recording each call."""

    verdict: Verdict = Verdict.SAFE
    policy: ToolPolicy = ToolPolicy.RESTRICTED
    summary: str = "scripted adjudication"
    turns: Sequence[tuple[Agent, str]] = ((Agent.ANALYST, "looks fine"),)
    calls: list[tuple[str, Clearance]] = field(default_factory=list)

    async def adjudicate(
        self, prompt: str, clearance: Clearance
    ) -> AsyncIterator[DialogueTurn | Adjudication]:
        self.calls.append((prompt, clearance))
        dialogue = []
        for agent, message in self.turns:
            turn = DialogueTurn(agent=agent, message=message, timestamp=time.time())
            dialogue.append(turn)
            yield turn
        yield Adjudication(
            verdict=self.verdict,
            policy=self.policy,
            confidence=0.9,
            summary=self.summary,
            dialogue=tuple(dialogue),
        )


@dataclass
class ScriptedChatModel:
    """Returns queued replies in order; a queued exception is raised instead."""

    replies: list[str | BaseException]
    calls: list[list[ChatMessage]] = field(default_factory=list)

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        self.calls.append(list(messages))
        if not self.replies:
            raise AssertionError("ScriptedChatModel ran out of replies")
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


@dataclass
class ScriptedUsageChatModel:
    """A :class:`UsageChatModel` double: queued replies first, then ``default``.

    A queued ``str`` is returned without token usage; a queued exception is raised.
    """

    replies: list[ChatCompletion | str | BaseException]
    default: ChatCompletion | None = None
    calls: list[list[ChatMessage]] = field(default_factory=list)

    async def complete_with_usage(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatCompletion:
        self.calls.append(list(messages))
        if self.replies:
            reply = self.replies.pop(0)
        elif self.default is not None:
            reply = self.default
        else:
            raise AssertionError("ScriptedUsageChatModel ran out of replies")
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, str):
            return ChatCompletion(text=reply)
        return reply
