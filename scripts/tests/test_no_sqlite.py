"""Sunset test: nothing SQLite-related remains outside approved exceptions (spec 0046)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CRITERION_LINE = re.compile(r"^- \*\*[A-Z]{2,5}-[A-Z]{2,10}-\d{3}\*\*.*$", re.MULTILINE)
STATUS_LINE = re.compile(r"^- \*\*Status:\*\*\s*(\w+)", re.MULTILINE)
PUSHED_SQLITE_MIGRATION = "supabase/migrations/20261108120000_domain_schemas.sql"


def _is_allowed_sqlite_path(rel: str) -> bool:
    return (
        rel == PUSHED_SQLITE_MIGRATION
        or rel == "CHANGELOG.md"
        or rel.startswith("specs/")
        or rel.startswith("docs/explanation/decisions/")
        or rel == "bun.lock"
        or rel == "scripts/tests/test_no_sqlite.py"
        # @nuxt/content v3 uses node:sqlite at build time for static prerendering (no runtime DB).
        or rel == "apps/landing/nuxt.config.ts"
    )


@pytest.mark.spec("DEV-SUPA-006")
def test_repository_has_no_sqlite_references_outside_historical_exceptions() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    unexpected: list[str] = []
    for rel in tracked:
        if _is_allowed_sqlite_path(rel):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "sqlite" in text.lower():
            unexpected.append(rel)

    assert unexpected == [], f"Unexpected sqlite references in: {unexpected}"

    bad_criteria: list[str] = []
    for spec in sorted(ROOT.glob("specs/[0-9]*/spec.md")):
        if spec.parent.name.startswith("0046-"):
            continue
        text = spec.read_text(encoding="utf-8")
        status = STATUS_LINE.search(text)
        if not status or status.group(1) not in {"Accepted", "Implemented"}:
            continue
        for match in CRITERION_LINE.finditer(text):
            if "sqlite" in match.group(0).lower():
                bad_criteria.append(f"{spec.relative_to(ROOT)}: {match.group(0)}")

    assert bad_criteria == []
