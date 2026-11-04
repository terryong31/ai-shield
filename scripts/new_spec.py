"""Scaffold ``specs/NNNN-<slug>/`` from the templates with the next free number."""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"


def main() -> int:
    if len(sys.argv) != 2 or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", sys.argv[1]):
        print("usage: mise run spec:new <kebab-case-slug>")
        return 2
    numbers = [int(p.name[:4]) for p in SPECS.glob("[0-9][0-9][0-9][0-9]-*")]
    number = f"{max(numbers, default=0) + 1:04d}"
    target = SPECS / f"{number}-{sys.argv[1]}"
    target.mkdir()

    title = sys.argv[1].replace("-", " ").capitalize()
    for template in ("spec.md", "plan.md", "tasks.md"):
        text = (SPECS / "_templates" / template).read_text(encoding="utf-8")
        text = text.replace("NNNN", number).replace("<Feature name>", title)
        text = text.replace("YYYY-MM-DD", dt.date.today().isoformat())
        (target / template).write_text(text, encoding="utf-8")

    print(f"created {target.relative_to(ROOT)}/ (spec.md, plan.md, tasks.md)")
    print("next: fill in spec.md, add it to specs/README.md, open a PR for review")
    return 0


if __name__ == "__main__":
    sys.exit(main())
