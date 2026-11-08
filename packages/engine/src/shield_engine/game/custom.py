"""Custom sandbox: a player's own agent, dataset and model (spec 0022).

The run is the same as a level wave (same board walk, canary, judge and score);
only the agent profile, the messages and the model come from the player.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable, Iterable, Mapping

from shield_engine.game import (
    AgentProfile,
    BoardGraph,
    BoardValidationError,
    LevelMessage,
    MessageTrace,
    WaveResult,
    evaluate_message,
    score_traces,
    validate_board,
)
from shield_engine.game.agent import new_canary
from shield_engine.ports import Classifier, UsageChatModel

CUSTOM_LEVEL_ID = "custom"
CUSTOM_MAX_ROWS = 50
CUSTOM_ROW_MAX_CHARS = 1000
CUSTOM_OBJECTIVE_MAX_CHARS = 1000
CUSTOM_MAX_TOOLS = 10
CUSTOM_TOOL_DESCRIPTION_MAX_CHARS = 200
CUSTOM_TOKENS_PER_PROMPT = 1000
CUSTOM_LATENCY_BUDGET_MS = 3000
CUSTOM_COST_PER_PROMPT_USD = 0.002

_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_NORMAL_LABELS = frozenset({"normal", "benign", "0"})
_ATTACK_LABELS = frozenset({"attack", "1"})


def validate_custom_profile(profile: AgentProfile) -> None:
    """Raise :class:`BoardValidationError` when a player's agent is outside the limits."""
    objective = profile.objective.strip()
    if not objective:
        raise BoardValidationError("The objective is required.")
    if len(objective) > CUSTOM_OBJECTIVE_MAX_CHARS:
        raise BoardValidationError("The objective must be at most 1,000 characters.")
    if len(profile.tools) > CUSTOM_MAX_TOOLS:
        raise BoardValidationError("The agent accepts at most 10 tools.")
    names = [tool.name for tool in profile.tools]
    if any(not _TOOL_NAME.match(name) for name in names):
        raise BoardValidationError("Tool names must be snake_case, up to 40 characters.")
    if len(set(names)) != len(names):
        raise BoardValidationError("Tool names must be unique.")
    if any(len(tool.description) > CUSTOM_TOOL_DESCRIPTION_MAX_CHARS for tool in profile.tools):
        raise BoardValidationError("Tool descriptions must be at most 200 characters.")


def build_custom_messages(
    rows: Iterable[Mapping[str, object]], profile: AgentProfile
) -> tuple[LevelMessage, ...]:
    """Turn dataset rows (``text``, ``label``, optional ``expected_tool``) into messages."""
    items = list(rows)
    if not items:
        raise BoardValidationError("The dataset has no rows.")
    if len(items) > CUSTOM_MAX_ROWS:
        raise BoardValidationError("The dataset has more than 50 rows.")
    tool_names = {tool.name for tool in profile.tools}
    messages: list[LevelMessage] = []
    for number, row in enumerate(items, start=1):
        text = str(row.get("text") or "").strip()
        label = str(row.get("label") or "").strip().lower()
        expected = str(row.get("expected_tool") or "").strip() or None
        if not text:
            raise BoardValidationError(f"Row {number}: text is empty.")
        if len(text) > CUSTOM_ROW_MAX_CHARS:
            raise BoardValidationError(f"Row {number}: text is over 1,000 characters.")
        if label not in _NORMAL_LABELS | _ATTACK_LABELS:
            raise BoardValidationError(f"Row {number}: label must be normal or attack.")
        if expected is not None and expected not in tool_names:
            raise BoardValidationError(
                f"Row {number}: expected_tool must be one of the agent's tools."
            )
        is_attack = label in _ATTACK_LABELS
        messages.append(
            LevelMessage(
                id=f"row-{number}",
                text=text,
                is_attack=is_attack,
                category="custom",
                expected_tool=None if is_attack else expected,
            )
        )
    return tuple(messages)


def parse_custom_dataset(csv_text: str, profile: AgentProfile) -> tuple[LevelMessage, ...]:
    """Parse ``text,label,expected_tool`` CSV into messages, naming the first bad row."""
    reader = csv.DictReader(io.StringIO(csv_text.strip() + "\n"))
    fields = {name.strip().lower() for name in reader.fieldnames or []}
    if not {"text", "label"} <= fields:
        raise BoardValidationError("The dataset needs text and label columns.")
    rows = [{(k or "").strip().lower(): v for k, v in row.items()} for row in reader]
    return build_custom_messages(rows, profile)


def _budgets(count: int) -> dict[str, float]:
    return {
        "token_budget": CUSTOM_TOKENS_PER_PROMPT * count,
        "max_latency_ms": CUSTOM_LATENCY_BUDGET_MS,
        "max_cost_usd": CUSTOM_COST_PER_PROMPT_USD * count,
    }


async def run_custom_wave(
    board: BoardGraph,
    *,
    profile: AgentProfile,
    messages: tuple[LevelMessage, ...],
    agent: UsageChatModel,
    classifier: Classifier | None = None,
    canary_factory: Callable[[], str] = new_canary,
) -> WaveResult:
    """Run every dataset message through the board and the player's agent, then score it."""
    validate_board(board)
    validate_custom_profile(profile)
    canary = canary_factory()
    traces: list[MessageTrace] = []
    for msg in messages:
        traces.append(
            await evaluate_message(
                board,
                message=msg.text,
                message_id=msg.id,
                is_attack=msg.is_attack,
                classifier=classifier,
                expected_tool=msg.expected_tool,
                agent=agent,
                canary=canary,
                agent_profile=profile,
            )
        )
    budgets = _budgets(len(messages))
    score = score_traces(
        messages,
        traces,
        token_budget=int(budgets["token_budget"]),
        max_latency_ms=budgets["max_latency_ms"],
        max_cost_usd=budgets["max_cost_usd"],
        classify_only=False,
    )
    return WaveResult(
        level_id=CUSTOM_LEVEL_ID, traces=tuple(traces), score=score, agent_mode="custom"
    )


async def run_custom_message(
    board: BoardGraph,
    *,
    profile: AgentProfile,
    message: str,
    agent: UsageChatModel,
    classifier: Classifier | None = None,
) -> WaveResult:
    """Score one player-written prompt as an attack against the player's own agent."""
    single = (LevelMessage("custom", message, True, "custom"),)
    result = await run_custom_wave(
        board, profile=profile, messages=single, agent=agent, classifier=classifier
    )
    return result
