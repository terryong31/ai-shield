"""Server-side storage and HMAC verification for player-trained ML models (spec 0045)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from shield_engine.game import ModelSignatureError, load_signed_model, sign_model
from shield_engine.ports import ProbabilityModel

logger = logging.getLogger(__name__)

MODEL_IDLE_TTL_SECONDS = 1800
MODEL_MAX_BYTES = 1_048_576
TRAIN_TIMEOUT_SECONDS = 10.0
CAMPAIGN_TRAIN_MAX_BYTES = 131_072
CUSTOM_TRAIN_MAX_BYTES = 1_310_720


class ModelTooLargeError(ValueError):
    """Raised when the signed model payload exceeds ``MODEL_MAX_BYTES``."""


def owner_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def account_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def signing_context(tok_hash: str, model_id: str) -> bytes:
    return f"{tok_hash}:{model_id}".encode()


class TrainedModelStore(Protocol):
    async def put(
        self,
        token: str,
        *,
        email: str,
        model_id: str,
        model: ProbabilityModel,
        signing_key: bytes,
    ) -> datetime: ...

    async def put_signed_blob(
        self,
        token: str,
        *,
        email: str,
        model_id: str,
        blob: bytes,
    ) -> datetime: ...

    async def get(
        self, token: str, model_id: str, *, signing_key: bytes
    ) -> ProbabilityModel | None: ...

    async def purge_session(self, token: str) -> None: ...

    async def purge_account(self, email: str, *, keep_token: str | None = None) -> None: ...


@dataclass
class _StoredEntry:
    model_id: str
    email_hash: str
    blob: bytes
    expires_at: float


class InMemoryTrainedModelStore:
    """In-memory per-session trained model store for tests and local dev."""

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._clock: Callable[[], float] = clock or time.monotonic
        self._entries: dict[str, _StoredEntry] = {}
        self._lock = asyncio.Lock()

    async def put_signed_blob(
        self,
        token: str,
        *,
        email: str,
        model_id: str,
        blob: bytes,
    ) -> datetime:
        if len(blob) > MODEL_MAX_BYTES:
            raise ModelTooLargeError("The trained model is too large. Use fewer rows.")
        tok_hash = owner_hash(token)
        async with self._lock:
            self._entries[tok_hash] = _StoredEntry(
                model_id=model_id,
                email_hash=account_hash(email),
                blob=blob,
                expires_at=self._clock() + MODEL_IDLE_TTL_SECONDS,
            )
        return datetime.now(UTC) + timedelta(seconds=MODEL_IDLE_TTL_SECONDS)

    async def put(
        self,
        token: str,
        *,
        email: str,
        model_id: str,
        model: ProbabilityModel,
        signing_key: bytes,
    ) -> datetime:
        tok_hash = owner_hash(token)
        blob = sign_model(model, key=signing_key, context=signing_context(tok_hash, model_id))
        return await self.put_signed_blob(token, email=email, model_id=model_id, blob=blob)

    async def get(
        self, token: str, model_id: str, *, signing_key: bytes
    ) -> ProbabilityModel | None:
        tok_hash = owner_hash(token)
        async with self._lock:
            entry = self._entries.get(tok_hash)
            if entry is None:
                return None
            if self._clock() >= entry.expires_at:
                del self._entries[tok_hash]
                return None
            if entry.model_id != model_id:
                return None
            try:
                model = load_signed_model(
                    entry.blob, key=signing_key, context=signing_context(tok_hash, model_id)
                )
            except ModelSignatureError:
                del self._entries[tok_hash]
                logger.warning("Signed ML model failed verification for session %s", tok_hash[:8])
                return None
            entry.expires_at = self._clock() + MODEL_IDLE_TTL_SECONDS
            return model

    async def purge_session(self, token: str) -> None:
        tok_hash = owner_hash(token)
        async with self._lock:
            self._entries.pop(tok_hash, None)

    async def purge_account(self, email: str, *, keep_token: str | None = None) -> None:
        e_hash = account_hash(email)
        keep_hash = owner_hash(keep_token) if keep_token else None
        async with self._lock:
            for tok_hash in [
                k for k, v in self._entries.items() if v.email_hash == e_hash and k != keep_hash
            ]:
                del self._entries[tok_hash]


class RedisTrainedModelStore:
    """Upstash/Redis-backed per-session trained model store (no filesystem usage)."""

    def __init__(self, redis_client: Any, *, clock: Callable[[], float] | None = None) -> None:
        self._redis = redis_client
        self._clock: Callable[[], float] = clock or time.monotonic

    @staticmethod
    def _model_key(tok_hash: str) -> str:
        return f"mlmodel:{tok_hash}"

    @staticmethod
    def _acct_key(e_hash: str) -> str:
        return f"mlmodels:acct:{e_hash}"

    @staticmethod
    def _encode_record(model_id: str, email_hash: str, blob: bytes) -> str:
        # Encode raw bytes via hex so UTF-8 string Redis clients stay lossless without extra deps.
        return f"{model_id}:{email_hash}:{blob.hex()}"

    @staticmethod
    def _decode_record(raw: str) -> tuple[str, str, bytes] | None:
        parts = raw.split(":")
        if len(parts) == 2:
            model_id, hex_blob = parts
            e_hash = ""
        elif len(parts) == 3:
            model_id, e_hash, hex_blob = parts
        else:
            return None
        try:
            return model_id, e_hash, bytes.fromhex(hex_blob)
        except ValueError:
            return None

    async def put_signed_blob(
        self,
        token: str,
        *,
        email: str,
        model_id: str,
        blob: bytes,
    ) -> datetime:
        if len(blob) > MODEL_MAX_BYTES:
            raise ModelTooLargeError("The trained model is too large. Use fewer rows.")
        tok_hash = owner_hash(token)
        e_hash = account_hash(email)
        mkey = self._model_key(tok_hash)
        akey = self._acct_key(e_hash)
        await self._redis.set(
            mkey, self._encode_record(model_id, e_hash, blob), ex=MODEL_IDLE_TTL_SECONDS
        )
        await self._redis.sadd(akey, tok_hash)
        await self._redis.expire(akey, MODEL_IDLE_TTL_SECONDS * 2)
        return datetime.now(UTC) + timedelta(seconds=MODEL_IDLE_TTL_SECONDS)

    async def put(
        self,
        token: str,
        *,
        email: str,
        model_id: str,
        model: ProbabilityModel,
        signing_key: bytes,
    ) -> datetime:
        tok_hash = owner_hash(token)
        blob = sign_model(model, key=signing_key, context=signing_context(tok_hash, model_id))
        return await self.put_signed_blob(token, email=email, model_id=model_id, blob=blob)

    async def get(
        self, token: str, model_id: str, *, signing_key: bytes
    ) -> ProbabilityModel | None:
        tok_hash = owner_hash(token)
        mkey = self._model_key(tok_hash)
        raw = await self._redis.get(mkey)
        if not isinstance(raw, str):
            return None
        parsed = self._decode_record(raw)
        if parsed is None:
            await self._redis.delete(mkey)
            return None
        stored_id, e_hash, blob = parsed
        if stored_id != model_id:
            return None
        try:
            model = load_signed_model(
                blob, key=signing_key, context=signing_context(tok_hash, model_id)
            )
        except ModelSignatureError:
            await self._redis.delete(mkey)
            logger.warning("Signed ML model failed verification for session %s", tok_hash[:8])
            return None
        await self._redis.expire(mkey, MODEL_IDLE_TTL_SECONDS)
        if e_hash:
            akey = self._acct_key(e_hash)
            await self._redis.sadd(akey, tok_hash)
            await self._redis.expire(akey, MODEL_IDLE_TTL_SECONDS * 2)
        return model

    async def purge_session(self, token: str) -> None:
        await self._redis.delete(self._model_key(owner_hash(token)))

    async def purge_account(self, email: str, *, keep_token: str | None = None) -> None:
        akey = self._acct_key(account_hash(email))
        keep_hash = owner_hash(keep_token) if keep_token else None
        members = await self._redis.smembers(akey)
        keys_to_delete = [
            self._model_key(str(m)) for m in members if keep_hash is None or str(m) != keep_hash
        ]
        if keys_to_delete:
            await self._redis.delete(*keys_to_delete)
        if keep_hash is None:
            await self._redis.delete(akey)
