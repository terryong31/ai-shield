# 0006. Hash-verified model artifacts

- **Status:** Accepted
- **Date:** 2026-09-23

## Context

The Layer 1 classifier is a scikit-learn vectorizer and model serialised with
joblib, which uses pickle. Unpickling executes arbitrary code, so whoever can
replace an artifact file can run code in every process that loads it. The
previous implementation loaded `model.pkl` and `vectorizer.pkl` without any
check and wrote the model back to disk on every
piece of reviewer feedback, so the committed artifact changed at runtime and
could not be traced to training data.

Alternatives considered: a non-executable format (ONNX, or exporting weights to
JSON), which would add conversion tooling and dependencies for a small research
baseline; signing artifacts, which needs key management; and recording content
digests at training time.

## Decision

- Bundled artifacts live in `shield_engine/models/baseline/` as
  `model.joblib` and `vectorizer.joblib`, with a `metadata.json` written in the
  same training run by `shield-engine train` (`mise run train`).
- `metadata.json` records the SHA-256 of each artifact, plus the algorithm,
  scikit-learn version, hyperparameters, and the training file's path, row
  count and SHA-256.
- `load_baseline()` verifies every digest **before** calling `joblib.load`, and
  raises `ArtifactIntegrityError` on a missing file or mismatch
  (ENG-CLS-006). The gateway therefore refuses to start with tampered artifacts.
- The engine never writes to its bundled artifacts. Online learning updates the
  in-memory model only; persisting it (`ClassifierDetector.save_model`) is the
  host's decision, to a path the host chooses.
- `.gitignore` excludes `*.pkl`; pickles are only allowed as hash-verified engine
  artifacts. The ruff rule against pickle loads (S301) is ignored only in
  `shield_engine/models/`.

## Consequences

- Accidental corruption, partial checkouts and naive tampering are caught at
  load time, before any code in the pickle runs.
- Each artifact is traceable to a training dataset digest and library version.
- Digests do not stop an attacker who can change both the artifacts and
  `metadata.json`; that is covered by repository access control and review.
  Only load artifacts you built.
- Training is byte-reproducible for fixed data, seed and scikit-learn
  version (the trainer strips a per-process cache from the vectorizer before
  pickling), so a digest change in a commit always means the data or a
  dependency changed. Behaviour is still compared with `mise run eval`.
- Reviewer feedback no longer improves the bundled model automatically;
  folding labels into the baseline is an explicit retraining step.
