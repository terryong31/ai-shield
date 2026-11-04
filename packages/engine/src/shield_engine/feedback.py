"""Feedback stores: human labels that override the classifier for exact prompts."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

_FIELDS = ("text", "label", "timestamp")


class InMemoryFeedbackStore:
    def __init__(self, labels: dict[str, int] | None = None) -> None:
        self._labels: dict[str, int] = dict(labels or {})

    def lookup(self, text: str) -> int | None:
        return self._labels.get(text)

    def record(self, text: str, label: int) -> None:
        self._labels[text] = label


class CsvFeedbackStore:
    """Append-only CSV log; the latest label for a prompt wins.

    The file is read once at construction and cached, so lookups are O(1)
    instead of re-parsing the file on every request.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._labels: dict[str, int] = {}
        if path.exists():
            with path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    self._labels[row["text"]] = int(row["label"])

    def lookup(self, text: str) -> int | None:
        return self._labels.get(text)

    def record(self, text: str, label: int) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self._path.exists()
        with self._path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=_FIELDS)
            if is_new:
                writer.writeheader()
            writer.writerow(
                {"text": text, "label": label, "timestamp": datetime.now(UTC).isoformat()}
            )
        self._labels[text] = label
