"""Wrap attacker-controlled text before an LLM reads it.

Prompts in the game are written by the attacker, so any model that reads one is
itself an injection target. The prompt travels as inert data inside
``<untrusted_prompt>`` tags, and look-alike tags inside it are neutralised so it
cannot close the wrapper early.
"""

from __future__ import annotations

import re

_DELIMITER_LOOKALIKE = re.compile(r"<\s*(?:/\s*)?untrusted_prompt\s*>", re.IGNORECASE)


def _neutralise(text: str) -> str:
    return _DELIMITER_LOOKALIKE.sub("[delimiter removed]", text)


def wrap_untrusted(prompt: str) -> str:
    return f"<untrusted_prompt>\n{_neutralise(prompt)}\n</untrusted_prompt>"
