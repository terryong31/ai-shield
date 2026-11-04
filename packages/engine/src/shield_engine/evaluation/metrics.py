from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


@dataclass(frozen=True, slots=True)
class BinaryMetrics:
    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def precision(self) -> float:
        return _ratio(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float:
        return _ratio(self.tp, self.tp + self.fn)

    @property
    def f1(self) -> float:
        return _ratio(2 * self.precision * self.recall, self.precision + self.recall)

    @property
    def false_positive_rate(self) -> float:
        return _ratio(self.fp, self.fp + self.tn)

    @property
    def accuracy(self) -> float:
        return _ratio(self.tp + self.tn, self.tp + self.fp + self.tn + self.fn)

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "false_positive_rate": self.false_positive_rate,
            "accuracy": self.accuracy,
        }


def compute_metrics(y_true: Sequence[int], y_pred: Sequence[int]) -> BinaryMetrics:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must be the same length")
    pairs = list(zip(y_true, y_pred, strict=True))
    return BinaryMetrics(
        tp=sum(1 for t, p in pairs if t == 1 and p == 1),
        fp=sum(1 for t, p in pairs if t == 0 and p == 1),
        tn=sum(1 for t, p in pairs if t == 0 and p == 0),
        fn=sum(1 for t, p in pairs if t == 1 and p == 0),
    )
