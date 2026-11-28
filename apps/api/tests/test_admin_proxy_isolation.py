"""Spec 0059: admin proxy secret isolation on production admin routes."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from shield_api.settings import Settings

from .conftest import ADMIN_EMAIL, ADMIN_PASSWORD, Harness

WEB_SECRET = "web-proxy-secret-value-0123456789"
ADMIN_SECRET = "admin-proxy-secret-value-9876543210"


@pytest.mark.spec("API-ADMIN-001")
def test_production_admin_routes_reject_web_proxy_and_accept_admin_proxy(
    harness: Harness,
) -> None:
    harness.container.settings = Settings(
        _env_file=None,
        APP_ENV="production",
        SESSION_COOKIE_SECURE=False,
        WEB_BASE_URL="https://play.ai-shield.my",
        CORS_ORIGINS=["https://play.ai-shield.my", "https://admin.ai-shield.my"],
        TRUSTED_CLIENT_IP_HEADER="x-shield-client-ip",
        TRUSTED_PROXY_SECRET=SecretStr(WEB_SECRET),
        API_ADMIN_PROXY_SECRET=SecretStr(ADMIN_SECRET),
    )

    web_headers = {
        "x-shield-proxy-secret": WEB_SECRET,
        "origin": "https://play.ai-shield.my",
        "sec-fetch-site": "same-origin",
    }
    assert harness.client.get("/api/v1/clearance", headers=web_headers).status_code == 403
    assert (
        harness.client.post(
            "/api/v1/clearance",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers=web_headers,
        ).status_code
        == 403
    )
    assert harness.client.delete("/api/v1/game/scores", headers=web_headers).status_code == 403

    admin_headers = {
        "x-shield-admin-proxy-secret": ADMIN_SECRET,
        "origin": "https://admin.ai-shield.my",
        "sec-fetch-site": "same-origin",
    }
    status_res = harness.client.get("/api/v1/clearance", headers=admin_headers)
    assert status_res.status_code == 200
    assert status_res.json()["granted"] is False

    grant_res = harness.client.post(
        "/api/v1/clearance",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers=admin_headers,
    )
    assert grant_res.status_code == 200
    assert grant_res.json()["granted"] is True
