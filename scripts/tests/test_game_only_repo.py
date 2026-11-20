"""The repository describes only the game (spec 0026)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUPERSEDED = ("0001", "0003", "0004", "0005", "0006", "0008", "0009", "0011", "0013", "0014")
NARROWED = ("0002", "0007", "0012", "0016", "0024")


def _spec(number: str) -> str:
    (folder,) = (ROOT / "specs").glob(f"{number}-*")
    return (folder / "spec.md").read_text(encoding="utf-8")


def _status(text: str) -> str:
    match = re.search(r"\*\*Status:\*\*\s*(.+)", text)
    assert match
    return match.group(1).strip()


@pytest.mark.spec("REPO-CLEAN-001")
def test_no_eval_task_and_legacy_specs_are_superseded_or_retired() -> None:
    tasks = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))["tasks"]
    assert "eval" not in tasks
    assert "train" in tasks

    for number in SUPERSEDED:
        assert _status(_spec(number)) == "Superseded by 0026", number
    for number in NARROWED:
        text = _spec(number)
        assert _status(text) == "Implemented", number
        assert "## Retired by 0026" in text, number

    readme = (ROOT / "specs" / "README.md").read_text(encoding="utf-8")
    for number in SUPERSEDED:
        row = next(line for line in readme.splitlines() if line.startswith(f"| {number} "))
        assert row.rstrip().endswith("| Superseded by 0026 |"), row
