import json
from pathlib import Path

import pytest

from shield_api.openapi import DEFAULT_PATH, render


@pytest.mark.spec("API-CONTRACT-001")
def test_only_versioned_routes_are_published() -> None:
    paths = json.loads(render())["paths"]

    assert all(path.startswith("/api/v1/") for path in paths)
    assert sorted(paths) == [
        "/api/v1/auth/account",  # spec 0025
        "/api/v1/auth/account/email",
        "/api/v1/auth/account/password",
        "/api/v1/auth/account/reset-progress",
        "/api/v1/auth/anonymous",
        "/api/v1/auth/confirm",  # spec 0047
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/recover",
        "/api/v1/auth/register",
        "/api/v1/auth/resend-confirmation",  # spec 0027
        "/api/v1/auth/reset-password",  # spec 0047
        "/api/v1/auth/session",
        "/api/v1/auth/upgrade",
        "/api/v1/clearance",
        "/api/v1/game/leaderboard",
        "/api/v1/game/leaderboard/me",
        "/api/v1/game/levels",
        "/api/v1/game/models",
        "/api/v1/game/models/purge",
        "/api/v1/game/progress",
        "/api/v1/game/run",
        "/api/v1/game/saves/{level_id}",  # spec 0023
        "/api/v1/game/scores",
        "/api/v1/game/train",
        "/api/v1/health",
    ]


@pytest.mark.spec("API-CONTRACT-001")
def test_committed_contract_is_up_to_date() -> None:
    committed = Path(DEFAULT_PATH).read_text(encoding="utf-8")

    assert committed == render(), "Contract drifted: run `mise run contract` and commit the result"
