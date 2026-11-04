"""Reproducible training for the baseline classifier."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier

from shield_engine.evaluation.dataset import Example
from shield_engine.models import METADATA_FILE, MODEL_FILE, VECTORIZER_FILE, sha256_file


def train_baseline(
    examples: list[Example],
    out_dir: Path,
    *,
    dataset_path: Path | None = None,
    replicate: int = 20,
    random_state: int = 42,
) -> dict[str, Any]:
    """Fit TF-IDF + SGD (log loss) and write artifacts plus ``metadata.json``.

    ``replicate`` repeats the (tiny) seed set so SGD sees enough updates to
    converge. Output is byte-for-byte reproducible for the same data, seed and
    scikit-learn version.
    """
    texts = [e.text for e in examples] * replicate
    labels = [e.label for e in examples] * replicate

    vectorizer = TfidfVectorizer(max_features=5000)
    features = vectorizer.fit_transform(texts)
    model = SGDClassifier(loss="log_loss", max_iter=1000, random_state=random_state)
    model.fit(features, labels)

    # A per-process id() cache sklearn would otherwise pickle, making digests
    # differ between identical runs.
    vectorizer.__dict__.pop("_stop_words_id", None)

    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_dir / MODEL_FILE)
    joblib.dump(vectorizer, out_dir / VECTORIZER_FILE)

    metadata: dict[str, Any] = {
        "name": out_dir.name,
        "algorithm": "TfidfVectorizer(max_features=5000) + SGDClassifier(loss=log_loss)",
        "sklearn_version": sklearn.__version__,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "hyperparameters": {"replicate": replicate, "random_state": random_state},
        "training_data": {
            "examples": len(examples),
            "path": dataset_path.as_posix() if dataset_path else None,
            "sha256": sha256_file(dataset_path) if dataset_path else None,
        },
        "files": {
            MODEL_FILE: sha256_file(out_dir / MODEL_FILE),
            VECTORIZER_FILE: sha256_file(out_dir / VECTORIZER_FILE),
        },
    }
    (out_dir / METADATA_FILE).write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata
