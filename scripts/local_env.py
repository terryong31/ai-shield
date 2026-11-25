"""Resolve local Supabase and Redis env vars from `supabase status -o json` (spec 0046)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

DEFAULT_LOCAL_REDIS_URL = "redis://localhost:6379/0"


def docker_supabase_url(url: str) -> str:
    """Rewrite loopback hosts to `host.docker.internal` for Docker containers."""
    parsed = urlparse(url)
    if parsed.hostname in {"127.0.0.1", "localhost"}:
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"host.docker.internal{port}"
        return urlunparse(parsed._replace(netloc=netloc))
    return url


def local_supabase_env(status_json: str, existing_env: Mapping[str, str]) -> dict[str, str]:
    """Build gateway env vars from `supabase status -o json` without overriding existing keys."""
    try:
        data = json.loads(status_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Local Supabase is not running. Run `mise run db:start` first.") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Local Supabase status is invalid. Run `mise run db:start` first.")

    api_url = str(data.get("API_URL") or "").strip()
    service_key = str(data.get("SERVICE_ROLE_KEY") or data.get("SECRET_KEY") or "").strip()
    if not api_url or not service_key:
        raise RuntimeError(
            "Local Supabase is missing API_URL or key. Run `mise run db:start` first."
        )

    merged = dict(existing_env)
    merged.setdefault("SUPABASE_URL", api_url)
    merged.setdefault("SUPABASE_KEY", service_key)
    merged.setdefault("REDIS_URL", DEFAULT_LOCAL_REDIS_URL)
    return merged


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            values[key] = value
    return values


def main(
    argv: list[str] | None = None,
    *,
    runner: Callable[..., Any] = subprocess.run,
    base_env: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    docker_mode = False
    if "--docker" in args:
        docker_mode = True
        args.remove("--docker")
    if "--" in args:
        args = args[args.index("--") + 1 :]
    if not args:
        print("Usage: local_env.py [--docker] -- <command...>", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parent.parent
    env_file = dotenv_path if dotenv_path is not None else root / "apps" / "api" / ".env"
    existing: dict[str, str] = {}
    existing.update(_read_dotenv(env_file))
    existing.update(os.environ if base_env is None else base_env)

    status = runner(
        ["supabase", "status", "-o", "json"], capture_output=True, text=True, check=False
    )
    if status.returncode != 0:
        print("Local Supabase is not running. Run `mise run db:start` first.", file=sys.stderr)
        return 1

    resolved = local_supabase_env(status.stdout, existing)
    if docker_mode:
        resolved["SUPABASE_URL"] = docker_supabase_url(resolved["SUPABASE_URL"])

    proc = runner(args, env=resolved, check=False)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
