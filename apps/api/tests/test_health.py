import pytest


@pytest.mark.spec("API-HEALTH-001")
def test_health_reports_model_status(harness) -> None:
    response = harness.client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["model_loaded"] is True
    assert body["storage_backend"] == "memory"
