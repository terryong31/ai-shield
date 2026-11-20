"""A local text classifier with a sensitive-topic floor (the game's ML filter baseline)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from shield_engine.types import Signal, Verdict

SENSITIVE_KEYWORDS: tuple[str, ...] = (
    "sales", "revenue", "employee", "salary", "database", "sql", "delete",
    "personal", "customer", "member", "boss", "org", "chart", "hierarchy",
    "email", "private", "confidential", "internal", "table", "drop",
)  # fmt: skip


class Vectorizer(Protocol):
    def transform(self, texts: list[str]) -> Any: ...


class ProbabilisticModel(Protocol):
    def predict_proba(self, features: Any) -> Any: ...


class ClassifierDetector:
    """Wraps any vectorizer + probabilistic classifier pair (e.g. TF-IDF + SGD)."""

    name = "classifier"

    def __init__(
        self,
        vectorizer: Vectorizer,
        model: ProbabilisticModel,
        *,
        malicious_threshold: float = 0.85,
        safe_threshold: float = 0.15,
        sensitive_keywords: Sequence[str] = SENSITIVE_KEYWORDS,
        sensitive_ceiling: float = 0.35,
        sensitive_floor: float = 0.40,
    ) -> None:
        if not 0.0 <= safe_threshold < malicious_threshold <= 1.0:
            raise ValueError("require 0 <= safe_threshold < malicious_threshold <= 1")
        self.vectorizer = vectorizer
        self.model = model
        self.malicious_threshold = malicious_threshold
        self.safe_threshold = safe_threshold
        self.sensitive_keywords = tuple(k.lower() for k in sensitive_keywords)
        self.sensitive_ceiling = sensitive_ceiling
        self.sensitive_floor = sensitive_floor

    def score(self, text: str) -> Signal:
        probability = float(self.model.predict_proba(self.vectorizer.transform([text]))[0][1])

        # Low scores on sensitive topics are pushed into UNCERTAIN so a later
        # check reviews them instead of this one waving them through.
        floored = probability < self.sensitive_ceiling and self._mentions_sensitive_topic(text)
        if floored:
            probability = self.sensitive_floor

        return Signal(
            detector=self.name,
            verdict=self._verdict_for(probability),
            score=probability,
            details={"sensitive_floor_applied": floored},
        )

    def _mentions_sensitive_topic(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in self.sensitive_keywords)

    def _verdict_for(self, probability: float) -> Verdict:
        if probability >= self.malicious_threshold:
            return Verdict.MALICIOUS
        if probability <= self.safe_threshold:
            return Verdict.SAFE
        return Verdict.UNCERTAIN
