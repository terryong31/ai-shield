"""Run the Playwright tests against the local stack (pre-push hook, `mise run e2e:gate`).

Uses the dev servers of this repository when they run. Otherwise it starts them without
Infisical and without provider or Stripe keys, and stops them at the end. Local Supabase
only: the script refuses another host.
"""

from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from local_env import local_supabase_env

ROOT = Path(__file__).resolve().parent.parent
WEB = "http://localhost:3000"
API = "http://localhost:8000"
EMAIL = "e2e@example.com"
START_SECONDS = 120
# Empty values override apps/api/.env, so a gate run can never call a paid service.
NO_KEYS = (
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "TYPESAFE_API_KEY",
    "JEV_API_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
)


class GateError(Exception):
    """The gate cannot run; the message says what to do."""


def require_local(url: str) -> str:
    """Return the URL, or refuse a host that is not this computer."""
    if urlparse(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise GateError("The e2e gate uses local Supabase only.")
    return url


def is_shield(url: str) -> bool:
    """True when the gateway of this project answers below the URL."""
    try:
        with urllib.request.urlopen(f"{url}/api/v1/health", timeout=5) as response:  # noqa: S310
            return json.load(response).get("service") == "AI S.H.I.E.L.D."
    except (OSError, ValueError, AttributeError):
        return False


def answers(url: str) -> bool:
    """True when something listens at the URL."""
    try:
        with urllib.request.urlopen(url, timeout=5):  # noqa: S310
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def admin_request(base: str, key: str, method: str, path: str, body: Any = None) -> Any:
    """Call the local Supabase Auth admin API."""
    request = urllib.request.Request(  # noqa: S310 (require_local checked the host)
        f"{base}/auth/v1/admin/{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
        return json.load(response)


def prepare_account(base: str, key: str) -> str:
    """Make the confirmed test account, with a new random password each run."""
    password = f"E2e-{secrets.token_urlsafe(18)}-1a"
    users = admin_request(base, key, "GET", "users?per_page=1000")["users"]
    user = next((u for u in users if u.get("email") == EMAIL), None)
    body = {"email": EMAIL, "password": password, "email_confirm": True}
    if user is None:
        admin_request(base, key, "POST", "users", body)
    else:
        admin_request(base, key, "PUT", f"users/{user['id']}", body)
    return password


def start_servers(env: dict[str, str], logs: Path) -> list[subprocess.Popen[bytes]]:
    """Start the gateway and the web client, each in its own process group."""
    commands = (
        ("api", ["uv", "run", "uvicorn", "shield_api.main:app", "--port", "8000"]),
        ("web", ["bun", "run", "dev"]),
    )
    processes = []
    for name, command in commands:
        with (logs / f"{name}.log").open("wb") as log:
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=ROOT / "apps" / name,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            )
    return processes


def stop_servers(processes: list[subprocess.Popen[bytes]]) -> None:
    """Stop each process group."""
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)


def wait_until_ready(processes: list[subprocess.Popen[bytes]], logs: Path) -> None:
    """Wait for the gateway through the web proxy."""
    deadline = time.monotonic() + START_SECONDS
    while time.monotonic() < deadline:
        if is_shield(WEB):
            return
        if any(process.poll() is not None for process in processes):
            break
        time.sleep(1)
    tail = "\n".join(
        (logs / f"{n}.log").read_text(errors="replace")[-1500:] for n in ("api", "web")
    )
    raise GateError(f"The local servers did not start.\n{tail}")


def run(logs: Path) -> int:
    """Prepare the local stack, run the tests, and return their exit code."""
    subprocess.run(["mise", "run", "infra:up"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        ["supabase", "migration", "up", "--local"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    status = subprocess.run(
        ["supabase", "status", "-o", "json"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    local = local_supabase_env(status.stdout, {})
    base = require_local(local["SUPABASE_URL"])
    password = prepare_account(base, local["SUPABASE_KEY"])

    processes: list[subprocess.Popen[bytes]] = []
    try:
        if not is_shield(WEB):
            if answers(WEB) or answers(API):
                raise GateError("Port 3000 or 8000 is in use by another program. Stop it first.")
            env = {**os.environ, **local, "APP_ENV": "development", "WEB_BASE_URL": WEB}
            env |= dict.fromkeys(NO_KEYS, "")
            env |= {"NUXT_API_PROXY_TARGET": API, "NUXT_PUBLIC_SITE_URL": WEB}
            processes = start_servers(env, logs)
            wait_until_ready(processes, logs)
        web = ROOT / "apps" / "web"
        subprocess.run(["bunx", "playwright", "install", "chromium"], cwd=web, check=True)
        tests = {**os.environ, "E2E_BASE_URL": WEB, "E2E_EMAIL": EMAIL, "E2E_PASSWORD": password}
        tests.pop("VERCEL_AUTOMATION_BYPASS_SECRET", None)
        return subprocess.run(["bunx", "playwright", "test"], cwd=web, env=tests).returncode
    finally:
        stop_servers(processes)


def main() -> int:
    """Run the gate and print a short reason when it cannot run."""
    with tempfile.TemporaryDirectory() as folder:
        try:
            return run(Path(folder))
        except GateError as err:
            sys.stderr.write(f"e2e gate: {err}\n")
        except subprocess.CalledProcessError as err:
            sys.stderr.write(f"e2e gate: `{' '.join(err.cmd[:3])}` failed.\n")
        except (OSError, RuntimeError) as err:
            sys.stderr.write(f"e2e gate: {err}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
