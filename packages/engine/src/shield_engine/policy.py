"""Deterministic mapping from a decision's tool policy to concrete tools.

This gate is plain code on purpose: even if an attacker talks the Layer 2
LLMs into a lenient verdict, they cannot unlock more than the policy allows.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from shield_engine.types import RiskLevel, ToolPolicy


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    risk: RiskLevel


def allowed_tools(policy: ToolPolicy, tools: Iterable[ToolSpec]) -> list[str]:
    """Names of the tools permitted under ``policy``, in catalogue order."""
    match policy:
        case ToolPolicy.ALLOW_ALL:
            return [tool.name for tool in tools]
        case ToolPolicy.RESTRICTED:
            return [tool.name for tool in tools if tool.risk is RiskLevel.LOW]
        case ToolPolicy.SHUTDOWN:
            return []
