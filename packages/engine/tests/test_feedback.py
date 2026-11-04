from pathlib import Path

from shield_engine import CsvFeedbackStore


def test_csv_store_persists_and_latest_label_wins(tmp_path: Path) -> None:
    path = tmp_path / "feedback" / "labels.csv"
    store = CsvFeedbackStore(path)
    store.record("a prompt, with a comma", 1)
    store.record("a prompt, with a comma", 0)

    reloaded = CsvFeedbackStore(path)

    assert reloaded.lookup("a prompt, with a comma") == 0
    assert reloaded.lookup("unknown") is None
