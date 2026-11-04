"""Groq adapter for the :class:`ChatModel` port. Requires ``shield-engine[groq]``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from shield_engine.ports import ChatMessage

try:
    from groq import AsyncGroq
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install the Groq extra: pip install 'shield-engine[groq]'") from exc


class GroqChatModel:
    def __init__(self, api_key: str, model: str, *, timeout: float = 30.0) -> None:
        self._client = AsyncGroq(api_key=api_key, timeout=timeout)
        self.model = model

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        # The SDK's per-role TypedDicts can't be inferred from a dynamic role.
        messages_payload: list[Any] = [{"role": m.role, "content": m.content} for m in messages]
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages_payload,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
