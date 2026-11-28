"""Spec 0061: production WEB_BASE_URL propagation for play.ai-shield.my."""

from __future__ import annotations

from pathlib import Path

import pytest

from shield_api.settings import Settings

from .conftest import Harness

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.spec("API-DOM-001")
def test_play_domain_propagates_to_supabase_config_and_auth_redirects(
    harness: Harness,
) -> None:
    harness.container.settings = Settings(
        _env_file=None,
        APP_ENV="development",
        WEB_BASE_URL="https://play.ai-shield.my",
        CORS_ORIGINS=["https://play.ai-shield.my", "https://admin.ai-shield.my"],
    )
    harness.auth.confirm_email = True
    res = harness.client.post(
        "/api/v1/auth/register",
        json={"email": "newplayer@ai-shield.my", "password": "Str0ngPassw0rd!"},
    )
    assert res.status_code in (200, 201, 202)
    assert any(
        str(entry.get("options", {}).get("email_redirect_to", "")).startswith(
            "https://play.ai-shield.my/auth/confirmed"
        )
        for entry in harness.auth.sign_ups
    )

    supa_config = (REPO / "supabase" / "config.toml").read_text(encoding="utf-8")
    assert 'site_url = "https://play.ai-shield.my"' in supa_config
    assert '"https://play.ai-shield.my/auth/confirmed"' in supa_config
    assert '"https://play.ai-shield.my/auth/reset-password"' in supa_config
