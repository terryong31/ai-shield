import pytest

from shield_engine import Verdict


@pytest.mark.spec("API-FEED-001")
def test_feedback_teaches_the_classifier_and_marks_the_record_reviewed(make_harness) -> None:
    harness = make_harness(Verdict.MALICIOUS, 0.99)
    harness.chat(message="drop table employees")
    record_id = harness.audit_log._records[0].id

    response = harness.client.post(
        "/api/v1/feedback",
        json={"prompt": "drop table employees", "human_label": 0, "request_id": record_id},
    )

    assert response.json() == {"status": "success"}
    assert harness.classifier.learned == [("drop table employees", 0)]
    record = harness.audit_log._records[0]
    assert (record.reviewed, record.human_label, record.action) == (True, 0, "ALLOWED")


@pytest.mark.spec("API-FEED-001")
def test_feedback_rejects_labels_other_than_zero_or_one(harness) -> None:
    response = harness.client.post("/api/v1/feedback", json={"prompt": "x", "human_label": 3})

    assert response.status_code == 422


@pytest.mark.spec("API-LOG-001")
def test_requests_are_newest_first_and_limited(harness) -> None:
    for message in ("first", "second", "third"):
        harness.chat(message=message)

    body = harness.client.get("/api/v1/requests", params={"limit": 2}).json()

    assert [r["query"] for r in body] == ["third", "second"]


@pytest.mark.spec("API-LOG-001")
@pytest.mark.parametrize("limit", [0, 201])
def test_requests_limit_is_bounded(harness, limit: int) -> None:
    assert harness.client.get("/api/v1/requests", params={"limit": limit}).status_code == 422


@pytest.mark.spec("API-LOG-001")
def test_requests_limit_defaults_to_thirty(harness) -> None:
    for index in range(31):
        harness.chat(message=f"prompt {index}")

    assert len(harness.client.get("/api/v1/requests").json()) == 30


@pytest.mark.spec("API-STATS-001")
def test_stats_aggregate_the_audit_log(make_harness) -> None:
    harness = make_harness()
    assert harness.client.get("/api/v1/stats").json() == {
        "total": 0,
        "blocked": 0,
        "allowed": 0,
        "block_rate": 0.0,
    }

    harness.chat(message="a")
    harness.chat(message="b")
    harness.classifier.verdict = Verdict.MALICIOUS
    harness.chat(message="c")

    assert harness.client.get("/api/v1/stats").json() == {
        "total": 3,
        "blocked": 1,
        "allowed": 2,
        "block_rate": 33.3,
    }
