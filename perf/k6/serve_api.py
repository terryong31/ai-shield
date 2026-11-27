"""Serve the real gateway with in-memory stores, for k6 runs on one machine (spec 0057).

Usage: uv run python perf/k6/serve_api.py --mode dev|prod --port 8000

`dev` is the development gateway. `prod` turns on the production rules: rate limits, the
proxy secret (`SHIELD_K6_PROXY_SECRET`) on every route and BotID on protected routes. No
store, model or payment provider leaves the process, so a run costs nothing.
"""

from __future__ import annotations

import argparse
import os
import secrets
from typing import Any

import uvicorn

from shield_api.container import Container
from shield_api.main import create_app
from shield_api.services.identity import InvalidIdentityError, VerifiedPlayer
from shield_api.services.scores import InMemoryScoreStore
from shield_api.settings import Settings
from shield_engine.models import load_baseline


class _NoAdmins:
    async def authenticate(self, email: str, password: str) -> None:
        return None


class _NoIdentity:
    """Every sign-in fails; the load tests sign in only to exercise the rate limits."""

    async def verify(self, email: str, password: str) -> VerifiedPlayer:
        raise InvalidIdentityError

    def __getattr__(self, name: str) -> Any:
        async def unavailable(*_: Any, **__: Any) -> Any:
            raise InvalidIdentityError

        return unavailable


def build_app(mode: str) -> Any:
    production = mode == "prod"
    secret = os.environ.get("SHIELD_K6_PROXY_SECRET") or secrets.token_urlsafe(32)
    settings = Settings(
        _env_file=None,
        APP_ENV="production" if production else "development",
        SESSION_COOKIE_SECURE=False,
        TRUSTED_PROXY_SECRET=secret,
        TRUSTED_CLIENT_IP_HEADER="x-shield-client-ip",
        MODEL_SIGNING_KEY=secrets.token_hex(32),
        WEB_BASE_URL="http://127.0.0.1:3000",
    )
    container = Container(
        settings=settings,
        classifier=load_baseline(),
        scores=InMemoryScoreStore(),
        admins=_NoAdmins(),
        identity=_NoIdentity(),
    )
    return create_app(container)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("dev", "prod"), default="dev")
    parser.add_argument("--port", type=int, default=8000)
    options = parser.parse_args()
    uvicorn.run(build_app(options.mode), host="127.0.0.1", port=options.port, log_level="warning")


if __name__ == "__main__":
    main()
