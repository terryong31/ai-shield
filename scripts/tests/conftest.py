import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

SPEC = """# 0042 — Example

- **Status:** {status}
- **Area:** ENG

## Acceptance criteria

- **ENG-EX-001**: first behaviour.
- **ENG-EX-002**: second behaviour.
"""

TASKS = """# tasks

- [ ] **ENG-EX-001**: red → green
- [ ] **ENG-EX-002**: red → green
- [ ] Update docs
"""


@pytest.fixture
def repo(tmp_path: Path):
    """A throwaway repository with one spec; returns a factory to set its status."""

    def make(status: str = "Accepted") -> Path:
        spec_dir = tmp_path / "specs" / "0042-example"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.md").write_text(SPEC.format(status=status))
        (spec_dir / "tasks.md").write_text(TASKS)
        return tmp_path

    return make
