"""Board validation: structure, tool policies and level constraints."""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Mapping

from shield_engine.game.agent import (
    AgentProfile,
    rules_error,
)
from shield_engine.game.levels import (
    GameLevel,
)
from shield_engine.game.types import (
    _DEFAULT_NODE_CAP,
    ALLOWED_ML_ALGORITHMS,
    MAX_MODEL_NODES,
    MODEL_NODE_KINDS,
    RETIRED_BLOCKED_MESSAGE,
    VALID_NODE_KINDS,
    BoardEdge,
    BoardGraph,
    BoardNode,
    BoardValidationError,
)


def _validate_tool_policy_config(node: BoardNode) -> None:
    if "tool_policy_enabled" in node.config and not isinstance(
        node.config["tool_policy_enabled"], bool
    ):
        raise BoardValidationError("tool_policy_enabled must be a boolean.")
    if node.kind in {"jev", "safety_check"} and "block_tools" in node.config:
        raw_bt = node.config["block_tools"]
        if not isinstance(raw_bt, list):
            raise BoardValidationError("block_tools must be a list of tool numbers or names.")
        for item in raw_bt:
            if isinstance(item, bool):
                raise BoardValidationError(
                    "block_tools entries must be 1-based tool numbers or tool names."
                )
            if isinstance(item, int):
                if item < 1 or item > 10:
                    raise BoardValidationError("block_tools numbers must be between 1 and 10.")
            elif isinstance(item, str):
                text = item.strip()
                if not text or len(text) > 40:
                    raise BoardValidationError(
                        "block_tools tool names must be between 1 and 40 characters."
                    )
            else:
                raise BoardValidationError(
                    "block_tools entries must be 1-based tool numbers or tool names."
                )


def _resolve_block_tools(raw_tools: object, profile: AgentProfile | None) -> tuple[str, ...]:
    if not isinstance(raw_tools, list | tuple):
        return ()
    resolved: list[str] = []
    seen: set[str] = set()
    tools = profile.tools if profile is not None else ()
    for item in raw_tools:
        if isinstance(item, bool):
            continue
        name: str | None = None
        idx: int | None = None
        if isinstance(item, int):
            idx = item
        elif isinstance(item, str):
            stripped = item.strip()
            lowered = stripped.lower()
            if stripped.isdigit():
                idx = int(stripped)
            elif lowered.startswith("tool ") and lowered[5:].strip().isdigit():
                idx = int(lowered[5:].strip())
            elif stripped:
                matching = next((t.name for t in tools if t.name.lower() == lowered), None)
                name = matching or stripped
        if idx is not None and 1 <= idx <= len(tools):
            name = tools[idx - 1].name
        if name and name.lower() not in seen:
            seen.add(name.lower())
            resolved.append(name)
    return tuple(resolved)


def validate_board(board: BoardGraph) -> None:
    """Ensure the board has required anchors, intermediate tool nodes, and no cycles."""
    node_by_id: dict[str, BoardNode] = {}
    for node in board.nodes:
        if node.kind == "blocked":
            raise BoardValidationError(RETIRED_BLOCKED_MESSAGE)
        if node.kind not in VALID_NODE_KINDS:
            raise BoardValidationError(f"Unknown node kind: {node.kind}")
        if node.id in node_by_id:
            raise BoardValidationError(f"Duplicate node id: {node.id}")
        if node.kind == "ml_classifier":
            algo = str(node.config.get("algorithm", "logistic_regression"))
            if algo not in ALLOWED_ML_ALGORITHMS:
                raise BoardValidationError(f"Unsupported ML algorithm: {algo}")
            if "safe_threshold" in node.config or "block_threshold" in node.config:
                safe_t = float(node.config.get("safe_threshold", 0.30))
                block_t = float(node.config.get("block_threshold", 0.75))
                if safe_t >= block_t:
                    raise BoardValidationError(
                        "ML filter safe_threshold must be less than block_threshold."
                    )
        if node.kind == "secret_scan":
            raw_patterns = node.config.get("patterns")
            if isinstance(raw_patterns, list):
                for pat in raw_patterns:
                    pat_str = str(pat).strip()
                    if len(pat_str) > 200:
                        raise BoardValidationError(
                            "Secret scanner regex must be at most 200 characters."
                        )
                    if pat_str:
                        try:
                            re.compile(pat_str, re.IGNORECASE)
                        except re.error as exc:
                            raise BoardValidationError(
                                f"Invalid secret scanner regex '{pat_str}': {exc}"
                            ) from exc
        if node.kind == "tool_filter":
            raw_rules = node.config.get("rules")
            if isinstance(raw_rules, list):
                for r in raw_rules:
                    if isinstance(r, Mapping) and str(r.get("condition")) == "match":
                        pat_str = str(r.get("pattern", "")).strip()
                        if len(pat_str) > 200:
                            raise BoardValidationError(
                                "Tool filter regex must be at most 200 characters."
                            )
                        if pat_str:
                            try:
                                re.compile(pat_str, re.IGNORECASE)
                            except re.error as exc:
                                raise BoardValidationError(
                                    f"Invalid tool filter regex '{pat_str}': {exc}"
                                ) from exc
        if node.kind == "jev":
            q_str = str(node.config.get("question", ""))
            if len(q_str) > 300:
                raise BoardValidationError("Jev noul question must be at most 300 characters.")
            _validate_tool_policy_config(node)
        if node.kind == "safety_check":
            _validate_tool_policy_config(node)
        if node.kind == "llm_review":
            prompt_str = str(node.config.get("prompt", ""))
            if len(prompt_str) > 1000:
                raise BoardValidationError(
                    "LLM review instructions must be at most 1000 characters."
                )
            _validate_tool_policy_config(node)
        if node.kind == "assistant":
            problem = rules_error(node.config.get("rules"))
            if problem:
                raise BoardValidationError(problem)
        node_by_id[node.id] = node

    kinds = [n.kind for n in board.nodes]
    for required in ("incoming", "assistant"):
        if kinds.count(required) != 1:
            raise BoardValidationError(f"Board must contain exactly one '{required}' node.")

    outgoing: dict[str, list[BoardEdge]] = {node.id: [] for node in board.nodes}
    in_degree: dict[str, int] = {node.id: 0 for node in board.nodes}

    for edge in board.edges:
        if edge.source not in node_by_id or edge.target not in node_by_id:
            raise BoardValidationError(
                f"Edge '{edge.id}' references unknown node '{edge.source}' or '{edge.target}'."
            )
        outgoing[edge.source].append(edge)
        in_degree[edge.target] += 1

    incoming_node = next(n for n in board.nodes if n.kind == "incoming")
    if not outgoing[incoming_node.id]:
        raise BoardValidationError("The 'input' node must have at least one outgoing wire.")

    queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for edge in outgoing[current]:
            in_degree[edge.target] -= 1
            if in_degree[edge.target] == 0:
                queue.append(edge.target)

    if visited != len(board.nodes):
        raise BoardValidationError("Board cannot contain a cycle.")


def _placeable_check_nodes(board: BoardGraph) -> tuple[BoardNode, ...]:
    return tuple(n for n in board.nodes if n.kind not in {"incoming", "assistant"})


def validate_board_for_level(board: BoardGraph, level: GameLevel) -> None:
    """Validate structural board rules plus level-specific Hard Constraints."""
    validate_board(board)
    check_nodes = _placeable_check_nodes(board)
    disabled = set(level.constraints.disabled_checks)
    for node in check_nodes:
        if node.kind in disabled:
            raise BoardValidationError(
                f"Check node '{node.kind}' is disabled in level '{level.id}'."
            )
    if len(check_nodes) > _DEFAULT_NODE_CAP:
        raise BoardValidationError(
            f"A board holds at most {_DEFAULT_NODE_CAP} check nodes (got {len(check_nodes)})."
        )
    model_nodes = sum(1 for n in check_nodes if n.kind in MODEL_NODE_KINDS)
    if model_nodes > MAX_MODEL_NODES:
        raise BoardValidationError(
            f"A board holds at most {MAX_MODEL_NODES} model nodes "
            f"(jev, safety check, LLM review); got {model_nodes}."
        )
    max_checks = level.constraints.max_check_nodes
    if max_checks is not None and len(check_nodes) > max_checks:
        raise BoardValidationError(
            f"Level '{level.id}' allows at most {max_checks} check nodes (got {len(check_nodes)})."
        )
