from __future__ import annotations

from dataclasses import dataclass

from shield_engine.types import ToolPolicy


@dataclass(frozen=True, slots=True)
class ShieldConfig:
    """Routing configuration for :class:`shield_engine.Shield`.

    Classification thresholds belong to the classifier itself; this only
    controls how signals are routed to a decision.
    """

    always_adjudicate: bool = False
    """Send every prompt through Layer 2, even ones Layer 1 considers safe."""

    skip_classifier: bool = False
    """Ablation switch: treat Layer 1 as SAFE/0.0 without consulting it."""

    default_policy: ToolPolicy = ToolPolicy.ALLOW_ALL
    """Tool policy for prompts that were never adjudicated."""
