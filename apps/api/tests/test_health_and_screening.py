import pytest

from shield_engine import Verdict


@pytest.mark.spec("API-HEALTH-001")
def test_health_reports_model_status(harness) -> None:
    response = harness.client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["model_loaded"] is True
    assert body["adjudication_enabled"] is True
    assert body["moderation_enabled"] is False


@pytest.mark.spec("API-STORE-005")
def test_health_reports_the_test_double_backend(harness) -> None:
    assert harness.client.get("/api/v1/health").json()["audit_backend"] == "memory"


@pytest.mark.spec("API-PRED-001")
def test_predict_returns_the_layer_one_signal(make_harness) -> None:
    harness = make_harness(Verdict.MALICIOUS, 0.97)

    body = harness.client.post("/api/v1/predict", json={"message": "drop table x"}).json()

    assert body == {
        "verdict": "MALICIOUS",
        "confidence_score": 0.97,
        "is_malicious": True,
        "override": False,
    }


@pytest.mark.spec("API-PRED-001")
@pytest.mark.parametrize("body", [{}, {"message": ""}])
def test_predict_rejects_malformed_bodies(harness, body) -> None:
    assert harness.client.post("/api/v1/predict", json=body).status_code == 422


@pytest.mark.spec("API-SCREEN-001")
def test_screen_returns_the_decision_without_the_assistant(make_harness) -> None:
    harness = make_harness(Verdict.UNCERTAIN, 0.5)

    body = harness.client.post("/api/v1/screen", json={"message": "salary table"}).json()

    assert body == {
        "verdict": "SAFE",
        "policy": "RESTRICTED",
        "blocked": False,
        "layer": "LAYER_2_DUAL_AGENT",
        "reason": "scripted adjudication",
        "ml_confidence": 0.5,
        "adjudicated": True,
    }
    assert harness.assistant.calls == []
