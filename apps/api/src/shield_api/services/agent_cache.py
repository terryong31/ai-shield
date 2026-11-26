"""Stored agent results, so the same board gets the same agent replies (spec 0050)."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections import OrderedDict
from collections.abc import Sequence

from shield_engine.ports import ChatCompletion, ChatMessage, UsageChatModel

_MAX_ENTRIES = 20_000


def level_canary(seed: str, level_id: str) -> str:
    """A canary fixed for each level, never shown, so equal boards send equal prompts."""
    digest = hmac.new(seed.encode("utf-8"), level_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"CANARY-{digest[:12].upper()}"


class AgentResultCache:
    """A bounded store of agent completions, keyed by model and the exact chat messages.

    The messages hold the level's agent prompt, the switched-off tools, the player's
    rules and the prompt, so the key covers all of them.
    """

    def __init__(self, max_entries: int = _MAX_ENTRIES) -> None:
        self._max = max_entries
        self._items: OrderedDict[str, ChatCompletion] = OrderedDict()

    @staticmethod
    def key(
        namespace: str,
        messages: Sequence[ChatMessage],
        temperature: float,
        max_tokens: int | None,
        thinking: bool,
    ) -> str:
        payload = json.dumps(
            {
                "ns": namespace,
                "m": [[m.role, m.content] for m in messages],
                "t": temperature,
                "x": max_tokens,
                "k": thinking,
            },
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> ChatCompletion | None:
        hit = self._items.get(key)
        if hit is not None:
            self._items.move_to_end(key)
        return hit

    def put(self, key: str, value: ChatCompletion) -> None:
        self._items[key] = value
        self._items.move_to_end(key)
        while len(self._items) > self._max:
            self._items.popitem(last=False)


class CachedChatModel:
    """Wraps an agent model; a stored result is returned without a provider call."""

    def __init__(self, inner: UsageChatModel, cache: AgentResultCache, namespace: str) -> None:
        self._inner = inner
        self._cache = cache
        self._namespace = namespace

    async def complete_with_usage(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        thinking: bool = False,
    ) -> ChatCompletion:
        key = AgentResultCache.key(self._namespace, messages, temperature, max_tokens, thinking)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        result = await self._inner.complete_with_usage(
            messages, temperature=temperature, max_tokens=max_tokens, thinking=thinking
        )
        self._cache.put(key, result)
        return result
