"""Groq adapter for the :class:`ChatModel` and :class:`UsageChatModel` ports.

Requires ``shield-engine[groq]``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from shield_engine.ports import ChatCompletion, ChatMessage

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
        completion = await self.complete_with_usage(
            messages, temperature=temperature, max_tokens=max_tokens
        )
        return completion.text

    def _reasoning_options(self, thinking: bool) -> dict[str, Any]:
        # Reasoning tokens count against max_tokens; unchecked, they leave an empty answer.
        # GPT-OSS cannot switch reasoning off, so "low" is its off setting.
        if self.model.startswith("openai/gpt-oss"):
            return {"reasoning_effort": "medium" if thinking else "low", "include_reasoning": False}
        if self.model.startswith("qwen/qwen3"):
            effort = "medium" if thinking else "none"
            return {"reasoning_effort": effort, "reasoning_format": "hidden"}
        return {}

    async def complete_with_usage(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        thinking: bool = False,
    ) -> ChatCompletion:
        # The SDK's per-role TypedDicts can't be inferred from a dynamic role.
        messages_payload: list[Any] = [{"role": m.role, "content": m.content} for m in messages]
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages_payload,
            temperature=temperature,
            max_tokens=max_tokens,
            **self._reasoning_options(thinking),
        )
        usage = response.usage
        return ChatCompletion(
            text=response.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )
