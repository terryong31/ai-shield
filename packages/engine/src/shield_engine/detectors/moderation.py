"""Llama Guard–style moderation behind the :class:`ChatModel` port."""

from __future__ import annotations

import re

from shield_engine.ports import ChatMessage, ChatModel
from shield_engine.types import ModerationResult

_CATEGORY_SEPARATORS = re.compile(r"[,\n]")


class LlamaGuardModerator:
    """Parses ``safe`` / ``unsafe\\nS1,S13`` replies into a :class:`ModerationResult`.

    ``fail_closed`` decides what a provider error means: by default the
    result is not flagged (moderation only ever escalates, so failing open
    cannot allow anything on its own).
    """

    def __init__(self, model: ChatModel, *, fail_closed: bool = False) -> None:
        self.model = model
        self.fail_closed = fail_closed

    async def moderate(self, text: str) -> ModerationResult:
        try:
            raw = await self.model.complete(
                [ChatMessage(role="user", content=text)], temperature=0.0, max_tokens=64
            )
        except Exception as exc:
            return ModerationResult(
                flagged=self.fail_closed,
                categories=("ERROR",) if self.fail_closed else (),
                error=str(exc),
            )

        raw = raw.strip()
        head, _, rest = raw.partition("\n")
        if head.strip().lower() == "safe":
            return ModerationResult(flagged=False, raw=raw)

        categories = tuple(c.strip() for c in _CATEGORY_SEPARATORS.split(rest) if c.strip())
        return ModerationResult(flagged=True, categories=categories, raw=raw)
