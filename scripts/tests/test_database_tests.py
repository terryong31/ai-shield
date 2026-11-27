"""Database tests are opt-in locally and run in CI (spec 0056)."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.spec("DEV-DB-001")
def test_api_tests_skip_db_tests_and_test_db_runs_them() -> None:
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "apps/api/tests", "--collect-only", "-q", "--no-cov"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert "tests/db/" not in collected
    assert "deselected" in collected

    marked = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "apps/api/tests/db",
            "-m",
            "db",
            "--collect-only",
            "-q",
            "--no-cov",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert "tests/db/test_db_privileges.py" in marked

    tasks = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]
    run = str(tasks["test:db"]["run"])
    assert "supabase test db" in run
    assert "pytest apps/api/tests/db -m db" in run
    assert "db:start" in tasks["test:db"]["depends"]
    for name in (
        "01_rls_and_privileges",
        "02_constraints_and_indexes",
        "03_daily_usage_rpcs",
        "04_purchase_rpcs",
    ):
        sql = (ROOT / "supabase" / "tests" / f"{name}.sql").read_text()
        assert "begin;" in sql.lower()
        assert "finish()" in sql
        assert "rollback;" in sql.lower()


@pytest.mark.spec("DEV-DB-002")
def test_ci_migrations_job_runs_the_database_tests() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    steps = workflow["jobs"]["migrations"]["steps"]
    commands = [str(step.get("run", "")) for step in steps]
    assert "mise run db:check" in commands
    assert "mise run test:db" in commands
    assert commands.index("mise run db:check") < commands.index("mise run test:db")
    affected = (ROOT / "scripts" / "affected.sh").read_text()
    assert "apps/api/tests/db" in affected
