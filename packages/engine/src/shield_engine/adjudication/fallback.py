from __future__ import annotations

from collections.abc import Sequence

from shield_engine.types import Adjudication, Clearance, DialogueTurn, ToolPolicy, Verdict


def fallback_adjudication(
    clearance: Clearance, summary: str, dialogue: Sequence[DialogueTurn] = ()
) -> Adjudication:
    """Conservative outcome used whenever Layer 2 cannot produce a real verdict.

    Cleared callers keep full access; everyone else is restricted to LOW-risk
    tools. Nothing is blocked outright, because Layer 1 already had its say.
    """
    granted = clearance is Clearance.GRANTED
    return Adjudication(
        verdict=Verdict.SAFE if granted else Verdict.UNCERTAIN,
        policy=ToolPolicy.ALLOW_ALL if granted else ToolPolicy.RESTRICTED,
        confidence=0.5,
        summary=summary,
        analysis=dialogue[0].message if dialogue else "",
        dialogue=tuple(dialogue),
        fallback=True,
    )
