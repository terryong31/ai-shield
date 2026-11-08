"""Bring-your-own-key models for the custom sandbox (spec 0022).

One vendor-neutral adapter speaks the OpenAI-compatible chat completions API,
which every allowlisted provider offers. Each provider's base URL is fixed here,
so a player can never point the gateway at another address (no SSRF). Adding a
provider is one entry in :data:`PROVIDERS`.

The key is held only by the client object built for one run. It is never logged,
never put in an exception message and never stored.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

import httpx

from shield_engine.ports import ChatCompletion, ChatMessage

ProviderId = Literal["openai", "anthropic", "google", "groq", "deepseek", "qwen", "moonshot"]

PROVIDERS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "moonshot": "https://api.moonshot.ai/v1",
}

PROVIDER_NAMES: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google Gemini",
    "groq": "Groq",
    "deepseek": "DeepSeek",
    "qwen": "Qwen (Alibaba Cloud)",
    "moonshot": "Kimi (Moonshot AI)",
}

BYOK_TIMEOUT_SECONDS = 30.0


class ProviderAuthError(RuntimeError):
    """The provider rejected the player's API key (HTTP 401 or 403)."""


class ProviderUnavailableError(RuntimeError):
    """The provider failed, timed out or returned something unusable."""


class OpenAICompatibleChatModel:
    """A :class:`UsageChatModel` over ``POST {base_url}/chat/completions``."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._url = f"{base_url}/chat/completions"
        self._api_key = api_key
        self._transport = transport

    def __repr__(self) -> str:  # never show the key
        return f"OpenAICompatibleChatModel(url={self._url!r}, model={self.model!r})"

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

    async def complete_with_usage(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatCompletion:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(
                timeout=BYOK_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.post(self._url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            # The exception text can include the request; keep only its type.
            raise ProviderUnavailableError(type(exc).__name__) from None
        if response.status_code in (401, 403):
            raise ProviderAuthError(f"HTTP {response.status_code}")
        if response.status_code >= 400:
            # Provider error bodies can echo part of the key, so they are dropped.
            raise ProviderUnavailableError(f"HTTP {response.status_code}")
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderUnavailableError("Unreadable response") from None
        usage = data.get("usage") or {}
        return ChatCompletion(
            text=str(text),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )


def build_byok_model(provider: str, model: str, api_key: str) -> OpenAICompatibleChatModel:
    """A client for one custom run. ``provider`` must be in :data:`PROVIDERS`."""
    return OpenAICompatibleChatModel(base_url=PROVIDERS[provider], model=model, api_key=api_key)
