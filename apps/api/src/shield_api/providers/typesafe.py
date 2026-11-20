"""TypeSafe System One (Jev) HTTP client (``POST https://api.typesafe.ai/v1/systemone``)."""

from __future__ import annotations

from typing import Any

import httpx

from shield_api.providers.byok import (
    BYOK_TIMEOUT_SECONDS,
    ProviderAuthError,
    ProviderUnavailableError,
)
from shield_engine.ports import JevEvaluation

TYPESAFE_SYSTEMONE_URL = "https://api.typesafe.ai/v1/systemone"


class HttpJevClient:
    """A :class:`JevClient` over ``POST https://api.typesafe.ai/v1/systemone``."""

    def __init__(
        self,
        *,
        api_key: str,
        url: str = TYPESAFE_SYSTEMONE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._url = url
        self._transport = transport

    def __repr__(self) -> str:
        return f"HttpJevClient(url={self._url!r})"

    async def evaluate_noul(
        self,
        state: str,
        question: str,
        *,
        model: str = "jev-latest",
    ) -> JevEvaluation:
        payload: dict[str, Any] = {
            "model": model,
            "state": state,
            "questions": {
                "check": {
                    "type": "noul",
                    "instructions": question,
                }
            },
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(
                timeout=BYOK_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.post(self._url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(type(exc).__name__) from None
        if response.status_code in (401, 403):
            raise ProviderAuthError(f"HTTP {response.status_code}")
        if response.status_code >= 400:
            raise ProviderUnavailableError(f"HTTP {response.status_code}")
        try:
            data = response.json()
            prob = float(data["answers"]["check"]["noul"])
            usage = data.get("usage") or {}
            in_tok = int(usage.get("input_tokens") or 0)
            out_tok = int(usage.get("output_tokens") or 0)
        except (ValueError, KeyError, TypeError):
            raise ProviderUnavailableError("Unreadable Jev response") from None
        return JevEvaluation(probability=prob, input_tokens=in_tok, output_tokens=out_tok)


def build_jev_client(api_key: str) -> HttpJevClient:
    """Build a per-run or container-level TypeSafe Jev client."""
    return HttpJevClient(api_key=api_key)
