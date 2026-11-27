"""Local onboarding without Infisical and repository polish (spec 0055)."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "with_secrets.py"


def _fake_infisical(directory: Path, *, logged_in: bool) -> None:
    script = directory / "infisical"
    status = 0 if logged_in else 1
    script.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "user" ]; then exit ' + str(status) + "; fi\n"
        'if [ "$1" = "run" ]; then shift; while [ "$1" != "--" ]; do shift; done; shift; '
        'INFISICAL_USED=1 exec "$@"; fi\n'
        "exit 2\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def _run(path_dirs: list[Path]) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.pathsep.join(str(d) for d in path_dirs),
        "HOME": os.environ.get("HOME", str(Path.home())),
    }
    probe = "import os; print('infisical' if os.environ.get('INFISICAL_USED') else 'direct')"
    return subprocess.run(
        [
            sys.executable,
            str(WRAPPER),
            "--env=dev",
            "--path=/api",
            "--",
            sys.executable,
            "-c",
            probe,
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.mark.spec("DEV-ONBOARD-001")
def test_dev_runner_falls_back_without_infisical(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    missing = _run([empty])
    assert missing.returncode == 0
    assert missing.stdout.strip() == "direct"
    assert "Infisical" in missing.stderr

    signed_out = tmp_path / "signed_out"
    signed_out.mkdir()
    _fake_infisical(signed_out, logged_in=False)
    fallback = _run([signed_out])
    assert fallback.stdout.strip() == "direct"
    assert "Infisical" in fallback.stderr

    signed_in = tmp_path / "signed_in"
    signed_in.mkdir()
    _fake_infisical(signed_in, logged_in=True)
    assert _run([signed_in]).stdout.strip() == "infisical"


@pytest.mark.spec("DEV-ONBOARD-001")
def test_dev_tasks_use_the_wrapper() -> None:
    tasks = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]
    for name in ("api:dev", "web:dev"):
        run = tasks[name]["run"]
        assert "scripts/with_secrets.py" in run, name
        assert not run.startswith("infisical run"), name


@pytest.mark.spec("DEV-ONBOARD-002")
def test_api_starts_through_the_dev_runner_without_infisical_or_keys(tmp_path: Path) -> None:
    probe = (
        "from fastapi.testclient import TestClient\n"
        "from shield_api.container import build_container\n"
        "from shield_api.main import create_app\n"
        "from shield_api.settings import Settings\n"
        "settings = Settings(_env_file=None)\n"
        "with TestClient(create_app(build_container(settings))) as client:\n"
        "    health = client.get('/api/v1/health').status_code\n"
        "    levels = len(client.get('/api/v1/game/levels').json()['levels'])\n"
        "print(health, levels)\n"
    )
    empty = tmp_path / "bin"
    empty.mkdir()
    env = {
        "PATH": os.pathsep.join([str(empty), str(Path(sys.executable).parent), "/usr/bin", "/bin"]),
        "HOME": os.environ.get("HOME", str(Path.home())),
        "APP_ENV": "development",
        "SUPABASE_URL": "http://127.0.0.1:54321",
        "SUPABASE_KEY": "sb_secret_local-development-key",
    }
    result = subprocess.run(
        [
            sys.executable,
            str(WRAPPER),
            "--env=dev",
            "--path=/api",
            "--",
            sys.executable,
            "-c",
            probe,
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=ROOT / "apps" / "api",
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().splitlines()[-1] == "200 19"


@pytest.mark.spec("DEV-ONBOARD-003")
def test_readme_getting_started_needs_no_infisical() -> None:
    readme = (ROOT / "README.md").read_text()
    start = readme.index("## Getting started")
    section = readme[start : readme.index("## Usage", start)]
    assert "mise run dev" in section
    assert ".env.example" in section
    assert "optional" in section.lower()
    assert "infisical login" in section


@pytest.mark.spec("DEV-POLISH-001")
def test_todo_file_is_gone() -> None:
    assert not (ROOT / "TODO.md").exists()


@pytest.mark.spec("DEV-POLISH-002")
def test_readme_has_the_demo_and_engineering_links() -> None:
    readme = (ROOT / "README.md").read_text()
    demo = ROOT / "docs" / "assets" / "gameplay-demo.webp"
    assert "docs/assets/gameplay-demo.webp" in readme
    assert demo.exists()
    assert demo.stat().st_size <= 5 * 1024 * 1024
    assert demo.read_bytes()[8:12] == b"WEBP"
    for link in (
        "docs/explanation/decisions",
        "contracts/shield-api.openapi.json",
        "packages/engine/MODEL_CARD.md",
    ):
        assert link in readme, link
