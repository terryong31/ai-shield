"""Bundled model artifacts, loaded only after their SHA-256 digests verify.

joblib files are pickles, and unpickling runs arbitrary code, so an artifact
is never deserialised unless it matches the digest recorded in
``metadata.json`` at training time.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import joblib

from shield_engine.detectors.classifier import ClassifierDetector

BASELINE_DIR = Path(__file__).resolve().parent / "baseline"
MODEL_FILE = "model.joblib"
VECTORIZER_FILE = "vectorizer.joblib"
METADATA_FILE = "metadata.json"


class ArtifactIntegrityError(RuntimeError):
    """An artifact is missing or does not match its recorded digest."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_metadata(directory: Path = BASELINE_DIR) -> dict[str, Any]:
    path = directory / METADATA_FILE
    if not path.exists():
        raise ArtifactIntegrityError(f"{METADATA_FILE} missing in {directory}")
    metadata: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return metadata


def verify_artifacts(directory: Path = BASELINE_DIR) -> dict[str, Any]:
    metadata = read_metadata(directory)
    for name, expected in metadata["files"].items():
        path = directory / name
        if not path.exists():
            raise ArtifactIntegrityError(f"{name} missing in {directory}")
        actual = sha256_file(path)
        if actual != expected:
            raise ArtifactIntegrityError(
                f"{name} digest mismatch: expected {expected}, got {actual}"
            )
    return metadata


def load_baseline(*, directory: Path = BASELINE_DIR, **kwargs: Any) -> ClassifierDetector:
    """Load the verified baseline TF-IDF + SGD classifier.

    Extra keyword arguments are forwarded to :class:`ClassifierDetector`
    (thresholds, feedback store, …).
    """
    verify_artifacts(directory)
    vectorizer = joblib.load(directory / VECTORIZER_FILE)
    model = joblib.load(directory / MODEL_FILE)
    return ClassifierDetector(vectorizer, model, **kwargs)
