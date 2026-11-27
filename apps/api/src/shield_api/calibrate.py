"""``mise run levels:calibrate``: run the difficulty proof with the real models (spec 0051).

For each level it runs the reference board 5 times, each lazy bot once and each generic one-node
bot once, with the gateway's configured models, and writes a report. It never runs in CI; CI
only checks the report (``mise run levels:check``). Model keys come from the environment
(Infisical); they are never written to the report.
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shield_api.container import build_game_models, check_model_for
from shield_api.settings import Settings
from shield_engine.game import (
    BoardValidationError,
    WaveResult,
    fit_classifier,
    get_levels,
    run_wave,
)
from shield_engine.game.calibration import (
    GENERIC_ONE_NODE_BOTS,
    BoardPlan,
    chain,
    lazy_bots,
    reference,
)
from shield_engine.ports import ChatCompletion, ChatMessage, ProbabilityModel, UsageChatModel

logger = logging.getLogger(__name__)
REFERENCE_RUNS = 5
_PARALLEL_LEVELS = 7
# Space the calls of each model a little, and wait out a 429 (rate limit) or 503 (busy).
_MIN_INTERVAL_S = 60 / 240
_RATE_LIMIT_WAIT_S = 65.0
_RATE_LIMIT_RETRIES = 6


def _rate_limited(exc: BaseException) -> bool:
    text = str(exc)
    # 429 is the rate limit; 503 is the provider's short "high demand" outage.
    return any(code in text for code in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"))


class _Throttled:
    """Spaces the calls of one model and retries a call that hits the provider rate limit."""

    def __init__(self, inner: UsageChatModel) -> None:
        self._inner = inner
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def complete_with_usage(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        thinking: bool = False,
    ) -> ChatCompletion:
        for attempt in range(_RATE_LIMIT_RETRIES + 1):
            async with self._lock:
                wait = self._last + _MIN_INTERVAL_S - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last = time.monotonic()
            try:
                return await self._inner.complete_with_usage(
                    messages, temperature=temperature, max_tokens=max_tokens, thinking=thinking
                )
            except Exception as exc:
                if not _rate_limited(exc) or attempt == _RATE_LIMIT_RETRIES:
                    raise
                logger.warning(
                    "provider busy (%s); waiting %.0f s", type(exc).__name__, _RATE_LIMIT_WAIT_S
                )
                await asyncio.sleep(_RATE_LIMIT_WAIT_S)
        raise AssertionError("unreachable")


class _Models:
    """The real models of a calibration run: agents per tier, Jev and review checks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        agents, self.jev_client = build_game_models(settings)
        self.game_agents: dict[Any, UsageChatModel] = {
            tier: _Throttled(model) for tier, model in agents.items()
        }

    def check_model_for(self, name: str) -> UsageChatModel | None:
        return check_model_for(self.settings, None, self.game_agents, name)


async def _live(container: _Models, level_id: str, plan: BoardPlan) -> WaveResult | None:
    models: dict[str, ProbabilityModel] = {}
    if plan.ml_rows:
        rows = [{"text": t, "label": label} for t, label in plan.ml_rows]
        models["ref"] = fit_classifier(algorithm=plan.ml_algorithm, rows=rows).model
    try:
        return await run_wave(
            plan.board,
            level_id=level_id,
            agents=container.game_agents,
            jev_client=container.jev_client,
            check_model=None,
            check_model_for=container.check_model_for,
            ml_models=models,
        )
    except BoardValidationError:
        return None


def _cleared(result: WaveResult | None) -> bool:
    return result is not None and result.score.won and result.stop is None


async def calibrate_level(container: _Models, level_id: str) -> dict[str, Any]:
    level = next(lv for lv in get_levels() if lv.id == level_id)
    ref = reference(level_id)
    runs = [await _live(container, level_id, ref.board) for _ in range(REFERENCE_RUNS)]
    totals = [r.score.total_score if r else 0 for r in runs]
    lazy = {
        name: await _live(container, level_id, plan) for name, plan in lazy_bots(level_id).items()
    }
    one_node: dict[str, dict[str, Any]] = {}
    for name, node in GENERIC_ONE_NODE_BOTS.items():
        result = await _live(container, level_id, BoardPlan(chain(node)))
        one_node[name] = {
            "cleared": _cleared(result),
            "attacks_stopped": result.score.attacks_protected if result else None,
            "normal_helped": result.score.benign_helped if result else None,
        }
    entry = {
        "level_id": level_id,
        "version": level.version,
        "reference_runs": REFERENCE_RUNS,
        "reference_clears": sum(_cleared(r) for r in runs),
        "reference_scores": totals,
        "reference_stdev": round(statistics.pstdev(totals), 1),
        "lazy_clears": sorted(name for name, r in lazy.items() if _cleared(r)),
        "one_node": one_node,
    }
    logger.info("calibrated %s: %s", level_id, json.dumps(entry))
    return entry


def _read_report(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return {e["level_id"]: e for e in json.loads(path.read_text("utf-8")).get("levels", [])}


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


async def calibrate(path: Path, level_ids: list[str] | None = None) -> None:
    settings = Settings()
    container = _Models(settings)
    wanted = level_ids or [lv.id for lv in get_levels()]
    existing = _read_report(path)
    # Levels run side by side; each model still spaces its own calls (_Throttled).
    gate = asyncio.Semaphore(_PARALLEL_LEVELS)

    async def one(level_id: str) -> tuple[str, dict[str, Any]]:
        async with gate:
            return level_id, await calibrate_level(container, level_id)

    for done in asyncio.as_completed([one(level_id) for level_id in wanted]):
        level_id, entry = await done
        existing[level_id] = entry
        report = {
            "date": datetime.now(UTC).isoformat(timespec="seconds"),
            "models": {
                "standard": settings.GAME_MODEL_STANDARD or settings.GEMINI_MODEL,
                "budget": settings.GAME_MODEL_BUDGET,
            },
            "levels": [existing[lv.id] for lv in get_levels() if lv.id in existing],
        }
        _write_report(path, report)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    args = sys.argv[1:]
    path = Path(args[0]) if args else Path("packages/engine/calibration/report.json")
    asyncio.run(calibrate(path, args[1:] or None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
