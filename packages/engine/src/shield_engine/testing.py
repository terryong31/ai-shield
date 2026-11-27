"""Deterministic test doubles for the engine's ports.

Shipped with the package so that host applications can test their
integration without network access or trained models.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from shield_engine.ports import ChatCompletion, ChatMessage, JevEvaluation
from shield_engine.types import Signal, Verdict

# The agent's closing turn after a tool ran (ENG-LADDER-012); no tokens, so totals stay as queued.
DONE_TURN = ChatCompletion(
    text='{"reply": "", "tool_calls": [], "refused": false}', input_tokens=0, output_tokens=0
)


@dataclass
class StaticClassifier:
    verdict: Verdict = Verdict.SAFE
    probability: float = 0.05
    calls: list[str] = field(default_factory=list)

    def score(self, text: str) -> Signal:
        self.calls.append(text)
        return Signal(detector="classifier", verdict=self.verdict, score=self.probability)


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
        thinking: bool = False,
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


@dataclass
class ScriptedJevClient:
    """A :class:`JevClient` test double: queued evaluations first, then ``default``."""

    replies: list[JevEvaluation | BaseException] = field(default_factory=list)
    default: JevEvaluation | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def evaluate_noul(
        self,
        state: str,
        question: str,
        *,
        model: str = "jev-latest",
    ) -> JevEvaluation:
        self.calls.append((state, question))
        if self.replies:
            reply = self.replies.pop(0)
        elif self.default is not None:
            reply = self.default
        else:
            raise AssertionError("ScriptedJevClient ran out of replies")
        if isinstance(reply, BaseException):
            raise reply
        return reply
