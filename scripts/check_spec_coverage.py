"""Fail if any acceptance criterion in an Accepted/Implemented spec has no test.

Criterion IDs look like ``ENG-PIPE-001`` and are defined in spec.md as
``- **ENG-PIPE-001**: …``. A criterion counts as covered when its ID appears
in any test file (pytest ``@pytest.mark.spec("…")`` or a Vitest test name).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFINITION = re.compile(r"^- \*\*([A-Z]{2,5}-[A-Z]{2,10}-\d{3})\*\*", re.MULTILINE)
STATUS = re.compile(r"^- \*\*Status:\*\*\s*(\w+)", re.MULTILINE)
ENFORCED = {"Accepted", "Implemented"}
TEST_GLOBS = (
    "packages/*/tests/**/*.py",
    "apps/*/tests/**/*.py",
    "apps/*/test/**/*.ts",
    "scripts/tests/**/*.py",
)


def _should_skip_during_sdd_verify(spec: Path, status: str, verify_spec: str | None) -> bool:
    """When sdd:verify runs for one spec, skip later Accepted specs (0042+) not in the cycle."""
    if not verify_spec or status != "Accepted":
        return False
    if spec.parent.name == verify_spec:
        return False
    prefix = spec.parent.name.split("-", 1)[0]
    return prefix.isdigit() and int(prefix) >= 42


def main() -> int:
    tests = "\n".join(
        path.read_text(encoding="utf-8") for pattern in TEST_GLOBS for path in ROOT.glob(pattern)
    )
    verify_spec = os.environ.get("SDD_VERIFY_SPEC")

    missing: list[str] = []
    unverified: list[str] = []
    checked = 0
    for spec in sorted(ROOT.glob("specs/[0-9]*/spec.md")):
        text = spec.read_text(encoding="utf-8")
        status = STATUS.search(text)
        if not status or status.group(1) not in ENFORCED:
            continue
        if _should_skip_during_sdd_verify(spec, status.group(1), verify_spec):
            continue
        if status.group(1) == "Implemented" and "\n## Verification" not in text:
            unverified.append(str(spec.relative_to(ROOT)))
        for criterion in DEFINITION.findall(text):
            checked += 1
            if criterion not in tests:
                missing.append(f"{criterion}  ({spec.relative_to(ROOT)})")

    if missing:
        print("Acceptance criteria without a test:")
        print("\n".join(f"  - {m}" for m in missing))
    if unverified:
        print("Implemented specs without a ## Verification record (close cycles with sdd:done):")
        print("\n".join(f"  - {u}" for u in unverified))
    if missing or unverified:
        return 1
    print(f"spec coverage OK: {checked} criteria, all traced to tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
