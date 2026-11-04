from __future__ import annotations

import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from shield_engine.evaluation.dataset import Example
from shield_engine.evaluation.metrics import BinaryMetrics, compute_metrics
from shield_engine.pipeline import Shield
from shield_engine.types import ScreeningContext, Verdict


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    metrics: BinaryMetrics
    examples: int
    abstention_rate: float
    latency_ms_p50: float
    latency_ms_p95: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "examples": self.examples,
            "metrics": self.metrics.as_dict(),
            "abstention_rate": self.abstention_rate,
            "latency_ms": {"p50": self.latency_ms_p50, "p95": self.latency_ms_p95},
        }


def _percentile(values: Sequence[float], q: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[q - 1]


async def evaluate(
    shield: Shield,
    examples: Sequence[Example],
    context: ScreeningContext | None = None,
) -> EvaluationReport:
    """Screen every example sequentially. Blocked counts as a positive prediction."""
    y_true: list[int] = []
    y_pred: list[int] = []
    latencies: list[float] = []
    abstentions = 0

    for example in examples:
        started = time.perf_counter()
        decision = await shield.screen(example.text, context)
        latencies.append((time.perf_counter() - started) * 1000)
        y_true.append(example.label)
        y_pred.append(1 if decision.blocked else 0)
        abstentions += decision.verdict is Verdict.UNCERTAIN

    return EvaluationReport(
        metrics=compute_metrics(y_true, y_pred),
        examples=len(examples),
        abstention_rate=abstentions / len(examples) if examples else 0.0,
        latency_ms_p50=_percentile(latencies, 50),
        latency_ms_p95=_percentile(latencies, 95),
    )
