import json
from pathlib import Path

import pytest

from shield_engine import Shield, Verdict
from shield_engine.cli import main
from shield_engine.evaluation import (
    DatasetError,
    Example,
    compute_metrics,
    evaluate,
    load_jsonl,
)
from shield_engine.testing import StaticClassifier


def write_jsonl(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.spec("ENG-EVAL-001")
@pytest.mark.parametrize(
    "bad_line",
    ["{not json", '{"label": 1}', '{"text": "x", "label": 2}', '{"text": 5, "label": 0}'],
)
def test_malformed_rows_name_their_line(tmp_path: Path, bad_line: str) -> None:
    path = write_jsonl(tmp_path / "d.jsonl", ['{"text": "ok", "label": 0}', bad_line])

    with pytest.raises(DatasetError, match="line 2"):
        load_jsonl(path)


@pytest.mark.spec("ENG-EVAL-001")
def test_valid_rows_load_with_optional_fields(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "d.jsonl",
        ['{"text": "a", "label": 1, "category": "jailbreak"}', "", '{"text": "b", "label": 0}'],
    )

    assert load_jsonl(path) == [
        Example(text="a", label=1, category="jailbreak"),
        Example(text="b", label=0),
    ]


@pytest.mark.spec("ENG-EVAL-002")
def test_metrics_match_hand_computed_values() -> None:
    #           TP TP FN FP TN TN
    y_true = [1, 1, 1, 0, 0, 0]
    y_pred = [1, 1, 0, 1, 0, 0]

    m = compute_metrics(y_true, y_pred)

    assert (m.tp, m.fp, m.tn, m.fn) == (2, 1, 2, 1)
    assert m.precision == pytest.approx(2 / 3)
    assert m.recall == pytest.approx(2 / 3)
    assert m.f1 == pytest.approx(2 / 3)
    assert m.false_positive_rate == pytest.approx(1 / 3)
    assert m.accuracy == pytest.approx(4 / 6)


@pytest.mark.spec("ENG-EVAL-002")
def test_zero_denominators_yield_zero() -> None:
    m = compute_metrics([0, 0], [0, 0])

    assert (m.precision, m.recall, m.f1, m.false_positive_rate) == (0.0, 0.0, 0.0, 0.0)
    assert compute_metrics([], []).accuracy == 0.0


@pytest.mark.spec("ENG-EVAL-003")
async def test_blocked_is_positive_and_uncertain_is_reported_as_abstention() -> None:
    class ByText:
        def score(self, text: str):
            verdict = {"bad": Verdict.MALICIOUS, "meh": Verdict.UNCERTAIN}.get(text, Verdict.SAFE)
            return StaticClassifier(verdict, 0.5).score(text)

    examples = [Example("bad", 1), Example("meh", 1), Example("fine", 0), Example("fine", 0)]

    report = await evaluate(Shield(ByText()), examples)

    assert (report.metrics.tp, report.metrics.fn, report.metrics.tn) == (1, 1, 2)
    assert report.abstention_rate == pytest.approx(0.25)
    assert report.latency_ms_p50 >= 0
    assert report.latency_ms_p95 >= report.latency_ms_p50


@pytest.mark.spec("ENG-EVAL-004")
def test_cli_writes_a_reproducible_report(tmp_path: Path) -> None:
    data = write_jsonl(
        tmp_path / "d.jsonl",
        ['{"text": "drop table employees", "label": 1}', '{"text": "hello", "label": 0}'],
    )
    report_path = tmp_path / "report.json"

    exit_code = main(["eval", "--data", str(data), "--report", str(report_path)])

    assert exit_code == 0
    report = json.loads(report_path.read_text())
    assert report["dataset"]["path"] == str(data)
    assert len(report["dataset"]["sha256"]) == 64
    assert report["engine_version"]
    assert {"precision", "recall", "f1", "false_positive_rate"} <= set(report["metrics"])
