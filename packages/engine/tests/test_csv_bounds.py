"""Bounded CSV parsing and Unicode cleaning (spec 0054, ENG-SEC-001)."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from typing import Any

import pytest

from shield_engine.game import BoardValidationError, parse_dataset_csv
from shield_engine.game import custom as custom_module
from shield_engine.game import detectors as detectors_module
from shield_engine.game.custom import CUSTOM_MAX_ROWS, parse_custom_dataset
from shield_engine.game.detectors import _clean_training_text


class _Counting:
    """Wraps a csv reader and counts the rows that the parser pulls from it."""

    def __init__(self, inner: Any, counter: list[int]) -> None:
        self._inner = inner
        self._counter = counter

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def __iter__(self) -> Iterator[Any]:
        return self

    def __next__(self) -> Any:
        row = next(self._inner)
        self._counter[0] += 1
        return row


def _counting(factory: Any, counter: list[int]) -> Any:
    def wrapped(*args: Any, **kwargs: Any) -> _Counting:
        return _Counting(factory(*args, **kwargs), counter)

    return wrapped


@pytest.mark.spec("ENG-SEC-001")
def test_training_csv_stops_reading_past_the_row_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    max_rows = 10
    rows = ["text,label"] + [f"row {i},1" for i in range(5000)]
    counter = [0]
    monkeypatch.setattr(detectors_module.csv, "reader", _counting(csv.reader, counter))
    with pytest.raises(BoardValidationError, match="rows"):
        parse_dataset_csv("\n".join(rows), max_rows=max_rows)
    assert counter[0] <= max_rows + 2


@pytest.mark.spec("ENG-SEC-001")
def test_custom_dataset_stops_reading_past_the_row_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = ["text,label"] + [f"row {i},attack" for i in range(5000)]
    counter = [0]
    monkeypatch.setattr(custom_module.csv, "DictReader", _counting(csv.DictReader, counter))
    profile = custom_module.AgentProfile(objective="Help.", tools=(), token_budget=100)
    with pytest.raises(BoardValidationError, match="rows"):
        parse_custom_dataset("\n".join(rows), profile)
    assert counter[0] <= CUSTOM_MAX_ROWS + 2


@pytest.mark.spec("ENG-SEC-001")
def test_training_text_drops_format_and_surrogate_characters() -> None:
    assert _clean_training_text("a​b‮c\ud800d", 1) == "abcd"
