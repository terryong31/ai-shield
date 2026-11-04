"""Layer 1: a local text classifier with a sensitive-topic floor and feedback overrides."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import joblib

from shield_engine.ports import FeedbackStore
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
        feedback: FeedbackStore | None = None,
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
        self.feedback = feedback

    def score(self, text: str) -> Signal:
        if self.feedback is not None:
            label = self.feedback.lookup(text)
            if label is not None:
                malicious = label == 1
                return Signal(
                    detector=self.name,
                    verdict=Verdict.MALICIOUS if malicious else Verdict.SAFE,
                    score=1.0 if malicious else 0.0,
                    override=True,
                )

        probability = float(self.model.predict_proba(self.vectorizer.transform([text]))[0][1])

        # Low scores on sensitive topics are pushed into UNCERTAIN so Layer 2
        # reviews them instead of Layer 1 waving them through.
        floored = probability < self.sensitive_ceiling and self._mentions_sensitive_topic(text)
        if floored:
            probability = self.sensitive_floor

        return Signal(
            detector=self.name,
            verdict=self._verdict_for(probability),
            score=probability,
            details={"sensitive_floor_applied": floored},
        )

    def learn(self, text: str, label: int) -> None:
        """Record a human label and nudge the model towards it (online SGD)."""
        if self.feedback is not None:
            self.feedback.record(text, label)
        partial_fit = getattr(self.model, "partial_fit", None)
        if partial_fit is not None:
            partial_fit(self.vectorizer.transform([text]), [label])

    def save_model(self, path: Path) -> None:
        """Persist the (possibly updated) model. The host decides where."""
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, path)

    def _mentions_sensitive_topic(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in self.sensitive_keywords)

    def _verdict_for(self, probability: float) -> Verdict:
        if probability >= self.malicious_threshold:
            return Verdict.MALICIOUS
        if probability <= self.safe_threshold:
            return Verdict.SAFE
        return Verdict.UNCERTAIN
