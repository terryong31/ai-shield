"""Path filters for CI jobs and Vercel builds."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
TARGETS = ("deploy-web", "deploy-api", "ci-web", "ci-python", "ci-database")


def _env(**extra: str) -> dict[str, str]:
    # Git hooks export GIT_DIR and similar; the throwaway repository must not inherit them.
    inherited = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "VERCEL_"))}
    return {**inherited, **extra}


def _git(root: Path, *args: str) -> str:
    identity = ("-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false")
    return subprocess.run(
        ["git", *identity, *args], cwd=root, env=_env(), check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(root: Path, *files: str) -> str:
    for file in files:
        path = root / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(path.read_text() + "x" if path.exists() else "x")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "c")
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "scripts").mkdir(parents=True)
    for name in ("affected.sh", "vercel_ignore.sh"):
        shutil.copy(SCRIPTS / name, root / "scripts" / name)
    _git(root, "init", "-qb", "main")
    _git(root, "config", "uploadpack.allowAnySHA1InWant", "true")
    _commit(root, "README.md", "apps/web/app/old.vue", "apps/api/index.py")
    return root


def _affected(root: Path, target: str, base: str) -> int:
    return subprocess.run(
        ["bash", "scripts/affected.sh", target, base], cwd=root, env=_env(), check=False
    ).returncode


def _ignore(root: Path, app: str, remote: Path, **env: str) -> int:
    return subprocess.run(
        ["bash", "../../scripts/vercel_ignore.sh", app],
        cwd=root / "apps" / app,
        env=_env(SHIELD_GIT_REMOTE=remote.as_uri(), **env),
        check=False,
    ).returncode


def _shallow_clone(project: Path, branch: str) -> Path:
    clone = project.parent / "clone"
    _git(
        project.parent,
        "clone",
        "-q",
        "--depth=1",
        "--branch",
        branch,
        project.as_uri(),
        str(clone),
    )
    return clone


@pytest.mark.parametrize(
    ("file", "expected"),
    [
        ("apps/web/app/app.vue", {"deploy-web", "ci-web"}),
        ("apps/web/public/llms.txt", {"deploy-web", "ci-web"}),
        ("apps/web/vercel.json", {"deploy-web", "ci-web"}),
        ("apps/web/test/a.test.ts", {"ci-web"}),
        ("apps/web/AGENTS.md", set()),
        ("bun.lock", {"deploy-web", "ci-web"}),
        ("apps/api/src/shield_api/main.py", {"deploy-api", "ci-python"}),
        ("packages/engine/src/shield_engine/types.py", {"deploy-api", "ci-python"}),
        ("packages/engine/tests/test_a.py", {"ci-python"}),
        ("uv.lock", {"deploy-api", "ci-python"}),
        ("supabase/migrations/1.sql", {"ci-python", "ci-database"}),
        ("contracts/shield-api.openapi.json", {"ci-web", "ci-python"}),
        (".github/workflows/ci.yml", {"ci-web", "ci-python", "ci-database"}),
        ("mise.toml", {"ci-web", "ci-python", "ci-database"}),
        ("docs/how-to/deploy.md", set()),
        ("specs/0001-a/spec.md", set()),
        ("README.md", set()),
    ],
)
def test_a_change_affects_only_the_parts_that_use_it(
    project: Path, file: str, expected: set[str]
) -> None:
    base = _git(project, "rev-parse", "HEAD")
    _commit(project, file)

    assert {t for t in TARGETS if _affected(project, t, base) == 0} == expected


def test_a_file_moved_out_of_an_app_still_affects_it(project: Path) -> None:
    base = _git(project, "rev-parse", "HEAD")
    (project / "docs").mkdir()
    _git(project, "mv", "apps/web/app/old.vue", "docs/old.vue")
    _git(project, "commit", "-qm", "move")

    assert _affected(project, "deploy-web", base) == 0


def test_errors_are_not_reported_as_unaffected(project: Path) -> None:
    assert _affected(project, "deploy-web", "0" * 40) == 2
    assert _affected(project, "unknown", "HEAD") == 2


def test_vercel_compares_with_the_last_deployed_commit_not_the_last_commit(project: Path) -> None:
    deployed = _git(project, "rev-parse", "HEAD")
    _commit(project, "apps/web/app/app.vue")
    _commit(project, "docs/a.md")
    env = {"VERCEL_ENV": "production", "VERCEL_GIT_PREVIOUS_SHA": deployed}

    assert _ignore(project, "web", project, **env) == 1
    assert _ignore(project, "api", project, **env) == 0


def test_vercel_compares_the_first_preview_of_a_branch_with_main(project: Path) -> None:
    _git(project, "switch", "-qc", "feature")
    _commit(project, "apps/api/index.py")
    _commit(project, "docs/a.md")
    _git(project, "switch", "-q", "main")
    _commit(project, "apps/web/app/app.vue")
    clone = _shallow_clone(project, "feature")

    assert _ignore(clone, "api", project, VERCEL_ENV="preview") == 1
    assert _ignore(clone, "web", project, VERCEL_ENV="preview") == 0


def test_vercel_fetches_a_base_that_the_shallow_clone_does_not_have(project: Path) -> None:
    deployed = _git(project, "rev-parse", "HEAD")
    _commit(project, "apps/web/app/app.vue")
    _commit(project, "docs/a.md")
    clone = _shallow_clone(project, "main")
    env = {"VERCEL_ENV": "production", "VERCEL_GIT_PREVIOUS_SHA": deployed}

    assert _ignore(clone, "web", project, **env) == 1
    assert _ignore(clone, "api", project, **env) == 0


def test_vercel_builds_when_the_base_is_unknown(project: Path) -> None:
    missing = {"VERCEL_GIT_PREVIOUS_SHA": "0" * 40}

    assert _ignore(project, "web", project, VERCEL_ENV="production") == 1
    assert _ignore(project, "web", project, VERCEL_ENV="production", **missing) == 1
    assert _ignore(project, "web", project.parent / "gone", VERCEL_ENV="preview") == 1
