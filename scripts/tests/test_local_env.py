"""Local Supabase and Redis launcher tests (spec 0046)."""

from __future__ import annotations

import importlib
import json
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

SAMPLE_STATUS = json.dumps(
    {
        "API_URL": "http://127.0.0.1:54321",
        "SERVICE_ROLE_KEY": "sb-secret-service-role-key",
    }
)
SAMPLE_STATUS_FALLBACK = json.dumps(
    {
        "API_URL": "http://localhost:54321",
        "SECRET_KEY": "sb-secret-key-only",
    }
)


@pytest.mark.spec("DEV-SUPA-001")
def test_mise_tasks_and_tools_reflect_supabase_only_stack() -> None:
    data = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
    tasks = data["tasks"]
    tools = data["tools"]

    assert "local:db:reset" not in tasks
    assert tasks["db:reset"]["run"] == "supabase db reset"
    assert "supabase" in tools
    assert tasks["setup"]["run"][0] == "mise install"
    assert "infra:up" in tasks
    assert "infra:up" in tasks["api:dev"].get("depends", [])
    assert set(tasks["dev"].get("depends", [])) >= {"api:dev", "web:dev"}
    assert "db:start" in tasks["up"].get("depends", [])


@pytest.mark.spec("DEV-SUPA-002")
def test_compose_uses_always_on_redis_and_host_supabase_with_no_volumes() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert {"redis", "api", "web"} <= set(services)
    assert "profiles" not in services["redis"]

    api = services["api"]
    assert "host.docker.internal:host-gateway" in api.get("extra_hosts", [])
    env = api.get("environment", {})
    assert env.get("REDIS_URL") == "${REDIS_URL:-redis://redis:6379/0}"
    assert "SUPABASE_URL" in env
    assert "SUPABASE_KEY" in env
    assert "volumes" not in api
    assert "volumes" not in compose


@pytest.mark.spec("DEV-SUPA-003")
def test_local_supabase_env_parses_status_and_preserves_existing_env() -> None:
    local_env = importlib.import_module("local_env")

    result = local_env.local_supabase_env(SAMPLE_STATUS, {})
    assert result["SUPABASE_URL"] == "http://127.0.0.1:54321"
    assert result["SUPABASE_KEY"] == "sb-secret-service-role-key"
    assert result["REDIS_URL"] == "redis://localhost:6379/0"

    fallback = local_env.local_supabase_env(SAMPLE_STATUS_FALLBACK, {})
    assert fallback["SUPABASE_KEY"] == "sb-secret-key-only"

    preserved = local_env.local_supabase_env(
        SAMPLE_STATUS,
        {"SUPABASE_URL": "https://cloud.supabase.co", "SUPABASE_KEY": "custom-key"},
    )
    assert preserved["SUPABASE_URL"] == "https://cloud.supabase.co"
    assert preserved["SUPABASE_KEY"] == "custom-key"

    for bad in ("", "not-json", "{}"):
        with pytest.raises(RuntimeError, match="mise run db:start"):
            local_env.local_supabase_env(bad, {})


@pytest.mark.spec("DEV-SUPA-004")
def test_docker_supabase_url_rewrites_loopback_hosts_only() -> None:
    local_env = importlib.import_module("local_env")

    assert (
        local_env.docker_supabase_url("http://127.0.0.1:54321")
        == "http://host.docker.internal:54321"
    )
    assert (
        local_env.docker_supabase_url("http://localhost:54321")
        == "http://host.docker.internal:54321"
    )
    assert local_env.docker_supabase_url("https://cloud.supabase.co") == "https://cloud.supabase.co"


@pytest.mark.spec("DEV-SUPA-005")
def test_launcher_docker_mode_passes_rewritten_env_without_leaking_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    local_env = importlib.import_module("local_env")
    captured: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> SimpleNamespace:
        if cmd[:2] == ["supabase", "status"]:
            return SimpleNamespace(returncode=0, stdout=SAMPLE_STATUS, stderr="")
        captured.append((cmd, dict(kwargs.get("env", {}))))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.chdir(tmp_path)
    rc = local_env.main(
        ["--docker", "--", "docker", "compose", "up", "--build"],
        runner=fake_run,
        base_env={},
        dotenv_path=tmp_path / "missing.env",
    )

    assert rc == 0
    assert list(tmp_path.iterdir()) == []
    assert len(captured) == 1
    cmd, env = captured[0]
    assert cmd == ["docker", "compose", "up", "--build"]
    assert env["SUPABASE_URL"] == "http://host.docker.internal:54321"
    assert env["SUPABASE_KEY"] == "sb-secret-service-role-key"
    out = capsys.readouterr()
    assert "sb-secret-service-role-key" not in out.out + out.err
