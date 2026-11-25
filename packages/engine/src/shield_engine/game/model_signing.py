"""Pure HMAC-SHA256 verification and serialisation helpers for fitted ML models (spec 0045)."""

from __future__ import annotations

import hashlib
import hmac
import pickle
import struct
from typing import cast

from shield_engine.ports import ProbabilityModel

_VERSION = 1
_MAC_SIZE = 32


class ModelSignatureError(Exception):
    """Raised when a signed model fails header or HMAC verification before unpickling."""


def _compute_mac(key: bytes, context: bytes, payload: bytes) -> bytes:
    message = struct.pack(">I", len(context)) + context + payload
    return hmac.new(key, message, hashlib.sha256).digest()


def sign_model(model: ProbabilityModel, *, key: bytes, context: bytes) -> bytes:
    """Serialise ``model`` and prepend a version byte plus context-bound HMAC-SHA256 tag."""
    payload = pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL)
    tag = _compute_mac(key, context, payload)
    return bytes([_VERSION]) + tag + payload


def load_signed_model(blob: bytes, *, key: bytes, context: bytes) -> ProbabilityModel:
    """Verify header + HMAC-SHA256 over ``context`` and payload before unpickling."""
    if len(blob) <= 1 + _MAC_SIZE or blob[0] != _VERSION:
        raise ModelSignatureError("Invalid signed model header.")
    tag = blob[1 : 1 + _MAC_SIZE]
    payload = blob[1 + _MAC_SIZE :]
    expected = _compute_mac(key, context, payload)
    if not hmac.compare_digest(tag, expected):
        raise ModelSignatureError("Model signature verification failed.")
    return cast(ProbabilityModel, pickle.loads(payload))  # noqa: S301
