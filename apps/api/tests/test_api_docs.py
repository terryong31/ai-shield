"""Interactive API docs only in development (spec 0007, API-DOCS-001)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from shield_api.main import create_app
from shield_api.openapi import render
from shield_api.settings import Settings

DOC_PATHS = ("/api/v1/docs", "/api/v1/redoc", "/api/v1/openapi.json")


def _client(**env: str) -> TestClient:
    # No `with`: the lifespan (container wiring) is not needed to serve the docs routes.
    return TestClient(create_app(settings=Settings(_env_file=None, **env)))  # type: ignore[call-arg, arg-type]


@pytest.mark.spec("API-DOCS-001")
def test_development_serves_swagger_ui_and_the_schema() -> None:
    client = _client(APP_ENV="development")

    docs = client.get("/api/v1/docs")
    assert docs.status_code == 200
    assert "swagger-ui" in docs.text.lower()
    assert client.get("/api/v1/openapi.json").json()["info"]["title"]
    assert client.get("/api/v1/redoc").status_code == 404


@pytest.mark.spec("API-DOCS-001")
@pytest.mark.parametrize("env", [{"APP_ENV": "production"}, {}])
def test_production_and_unset_serve_no_docs_or_schema(env: dict[str, str]) -> None:
    # Production refuses callers without the proxy secret first (API-SEC-013), so the
    # test proves the secret and then finds no docs routes.
    secret = "p" * 40
    client = _client(**env, TRUSTED_PROXY_SECRET=secret)

    for path in DOC_PATHS:
        assert client.get(path).status_code == 403, path
        res = client.get(path, headers={"x-shield-proxy-secret": secret})
        assert res.status_code == 404, path


@pytest.mark.spec("API-DOCS-001")
def test_unknown_app_env_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, APP_ENV="staging")  # type: ignore[call-arg, arg-type]


@pytest.mark.spec("API-DOCS-001")
def test_contract_export_is_the_same_in_both_modes() -> None:
    # render() builds the app with defaults, which is production (no docs routes).
    dev = create_app(settings=Settings(_env_file=None, APP_ENV="development")).openapi()  # type: ignore[call-arg, arg-type]
    assert json.loads(render()) == dev
    assert dev["paths"]
