"""Deterministic detectors, training-row validation and classifier fitting."""

from __future__ import annotations

import base64
import csv
import io
import itertools
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

from shield_engine.game.types import (
    _BASE64_CANDIDATE_RE,
    _HEX_URL_RE,
    _ZERO_WIDTH_RE,
    ALLOWED_ML_ALGORITHMS,
    BoardGraph,
    BoardValidationError,
    CleanedText,
    FittedClassifier,
    MLAlgorithmKind,
    TrainingSummary,
    WordFilterResult,
)


class WordFilterDetector:
    """Fast edge phrase filter."""

    def __init__(self, custom_words: tuple[str, ...] | list[str] = ()) -> None:
        self._phrases = tuple(str(w).strip().lower() for w in custom_words if str(w).strip())

    def check(self, text: str) -> WordFilterResult:
        lowered = text.lower()
        for phrase in self._phrases:
            if phrase in lowered:
                return WordFilterResult(blocked=True, matched_rule=phrase)
        return WordFilterResult(blocked=False, matched_rule=None)


class TextCleaner:
    """Normalises zero-width characters and unpacks inline base64 or hex/URL segments."""

    def __init__(
        self,
        transforms: tuple[str, ...] | list[str] = ("strip_zero_width", "decode_base64"),
    ) -> None:
        self._transforms = tuple(str(t) for t in transforms)

    def clean(self, text: str) -> CleanedText:
        working = text
        modified = False
        if "strip_zero_width" in self._transforms:
            stripped = _ZERO_WIDTH_RE.sub("", working)
            if stripped != working:
                modified = True
            working = stripped

        decoded_parts: list[str] = []
        if "decode_base64" in self._transforms:
            for match in _BASE64_CANDIDATE_RE.finditer(working):
                token = match.group(0)
                if len(token) % 4 != 0:
                    continue
                try:
                    raw = base64.b64decode(token, validate=True)
                    decoded = raw.decode("utf-8")
                except (ValueError, UnicodeDecodeError):
                    decoded = ""
                if decoded and decoded.isprintable() and any(ch.isalpha() for ch in decoded):
                    decoded_parts.append(decoded)
                    modified = True

        if "decode_hex_url" in self._transforms:
            for match in _HEX_URL_RE.finditer(working):
                seq = match.group(0).replace("\\x", "%")
                hex_bytes = bytes(
                    int(seq[i + 1 : i + 3], 16)
                    for i in range(0, len(seq), 3)
                    if seq[i : i + 1] == "%"
                )
                try:
                    decoded_hex = hex_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    decoded_hex = ""
                if (
                    decoded_hex
                    and decoded_hex.isprintable()
                    and any(ch.isalpha() for ch in decoded_hex)
                ):
                    decoded_parts.append(decoded_hex)
                    modified = True

        if decoded_parts:
            working = f"{working} [unpacked: {' '.join(decoded_parts)}]"

        return CleanedText(text=working, was_modified=modified)


_TRAINING_MAX_TEXT_CHARS = 500


# Control, format (zero-width, bidi overrides) and surrogate characters (spec 0054).
_DROPPED_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})


def _clean_training_text(raw: Any, row_num: int) -> str:
    if not isinstance(raw, str):
        raise BoardValidationError(f"Row {row_num} text must be a string.")
    chars: list[str] = []
    for ch in raw:
        if ch in ("\t", "\n", "\r"):
            chars.append(" ")
        elif unicodedata.category(ch) in _DROPPED_CATEGORIES:
            continue
        else:
            chars.append(ch)
    cleaned = unicodedata.normalize("NFC", "".join(chars)).strip()
    if not cleaned:
        raise BoardValidationError(f"Row {row_num} has no text.")
    if len(cleaned) > _TRAINING_MAX_TEXT_CHARS:
        raise BoardValidationError(
            f"Row {row_num} is longer than {_TRAINING_MAX_TEXT_CHARS} characters."
        )
    return cleaned


def _parse_training_label(raw: Any, row_num: int) -> int:
    if isinstance(raw, bool):
        raise BoardValidationError(f"Row {row_num} has label {raw!r}; use 0, 1, safe or attack.")
    if isinstance(raw, int):
        if raw in (0, 1):
            return raw
        raise BoardValidationError(f"Row {row_num} has label {raw!r}; use 0, 1, safe or attack.")
    if isinstance(raw, str):
        norm = raw.strip().lower()
        if norm in ("0", "safe"):
            return 0
        if norm in ("1", "attack"):
            return 1
    raise BoardValidationError(f"Row {row_num} has label {raw!r}; use 0, 1, safe or attack.")


def validate_training_rows(
    rows: Sequence[Mapping[str, Any] | tuple[Any, Any]] | None,
    *,
    max_rows: int = 200,
) -> list[tuple[str, int]]:
    """Validate, clean, and normalize training rows (spec 0045)."""
    items = list(rows) if rows is not None else []
    if len(items) > max_rows:
        raise BoardValidationError(f"Dataset exceeds the maximum of {max_rows} rows.")
    cleaned: list[tuple[str, int]] = []
    for idx, item in enumerate(items, start=1):
        if isinstance(item, Mapping):
            raw_text = item.get("text")
            raw_label = item.get("label")
        elif isinstance(item, tuple) and len(item) == 2:
            raw_text, raw_label = item
        else:
            raise BoardValidationError(f"Row {idx} must have exactly 2 columns.")
        text = _clean_training_text(raw_text, idx)
        label = _parse_training_label(raw_label, idx)
        cleaned.append((text, label))
    if len(cleaned) < 2:
        raise BoardValidationError("Dataset must contain at least 2 rows with text and label.")
    if len({lbl for _, lbl in cleaned}) < 2:
        raise BoardValidationError(
            "Training dataset must include both safe (0) and attack (1) examples."
        )
    return cleaned


def parse_dataset_csv(csv_text: str, *, max_rows: int = 200) -> list[tuple[str, int]]:
    """Parse a strict ``text,label`` CSV string into cleaned ``(text, label)`` pairs."""
    trimmed = csv_text.strip()
    if not trimmed:
        raise BoardValidationError("The first row must be the header text,label.")
    reader = csv.reader(io.StringIO(trimmed))
    # Read at most the header, max_rows rows and one more to detect overflow (spec 0054).
    all_rows = list(itertools.islice(reader, max_rows + 2))
    if len(all_rows) > max_rows + 1:
        raise BoardValidationError(f"The dataset has more than {max_rows} rows.")
    if not all_rows or [c.strip().lower() for c in all_rows[0]] != ["text", "label"]:
        raise BoardValidationError("The first row must be the header text,label.")
    pairs: list[tuple[str, Any]] = []
    for idx, parts in enumerate(all_rows[1:], start=1):
        if len(parts) != 2:
            raise BoardValidationError(f"Row {idx} must have exactly 2 columns.")
        pairs.append((parts[0], parts[1]))
    return validate_training_rows(pairs, max_rows=max_rows)


def _build_sklearn_pipeline(algorithm: str) -> Pipeline:
    if algorithm not in ALLOWED_ML_ALGORITHMS:
        allowed_str = ", ".join(ALLOWED_ML_ALGORITHMS)
        raise BoardValidationError(
            f"Unsupported ML algorithm '{algorithm}'. Choose one of: {allowed_str}."
        )
    if algorithm == "logistic_regression":
        clf: Any = LogisticRegression(max_iter=200, random_state=42)
    elif algorithm in {"tfidf", "linear_svm"}:
        clf = SGDClassifier(loss="log_loss", max_iter=200, random_state=42)
    elif algorithm == "naive_bayes":
        clf = MultinomialNB(alpha=0.5)
    else:
        clf = RandomForestClassifier(n_estimators=25, random_state=42)
    return Pipeline(
        [("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000)), ("clf", clf)]
    )


def fit_classifier(
    *,
    algorithm: str,
    rows: Sequence[Mapping[str, Any] | tuple[Any, Any]] | None,
    max_rows: int = 200,
) -> FittedClassifier:
    """Validate rows and fit an allowlisted ML classifier once."""
    if algorithm not in ALLOWED_ML_ALGORITHMS:
        allowed_str = ", ".join(ALLOWED_ML_ALGORITHMS)
        raise BoardValidationError(
            f"Unsupported ML algorithm '{algorithm}'. Choose one of: {allowed_str}."
        )
    cleaned = validate_training_rows(rows, max_rows=max_rows)
    texts = [t for t, _ in cleaned]
    labels = [lbl for _, lbl in cleaned]
    pipe = _build_sklearn_pipeline(algorithm)
    pipe.fit(texts, labels)
    preds = pipe.predict(texts)
    correct = sum(1 for p, y in zip(preds, labels, strict=False) if int(p) == y)
    accuracy = round(correct / len(labels), 4)
    alg_literal: MLAlgorithmKind = algorithm
    return FittedClassifier(
        model=pipe,
        algorithm=alg_literal,
        sample_count=len(cleaned),
        accuracy=accuracy,
    )


def strip_training_data(board: BoardGraph) -> BoardGraph:
    """Return a copy of ``board`` with ``model_id`` and ``dataset`` stripped from ML filters."""
    stripped_nodes = tuple(
        replace(
            node,
            config={k: v for k, v in node.config.items() if k not in ("model_id", "dataset")},
        )
        if node.kind == "ml_classifier"
        else node
        for node in board.nodes
    )
    return replace(board, nodes=stripped_nodes)


def train_custom_classifier(
    *,
    algorithm: str,
    dataset: Sequence[Mapping[str, Any] | tuple[Any, Any]] | None = None,
    csv_text: str | None = None,
    max_rows: int = 200,
) -> TrainingSummary:
    """Validate and fit an allowlisted scikit-learn algorithm without echoing rows."""
    rows = parse_dataset_csv(csv_text, max_rows=max_rows) if csv_text is not None else dataset
    fitted = fit_classifier(algorithm=algorithm, rows=rows, max_rows=max_rows)
    return TrainingSummary(
        algorithm=fitted.algorithm,
        sample_count=fitted.sample_count,
        accuracy=fitted.accuracy,
    )
