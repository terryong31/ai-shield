# 0038 — ML filter user-defined training data only (no pre-trained TF-IDF baseline)

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-19
- **Related:** [0029-strict-win-lose-and-tool-config](../0029-strict-win-lose-and-tool-config/spec.md), [0035-merge-quick-screen-into-ml-filter](../0035-merge-quick-screen-into-ml-filter/spec.md)

## Problem

1. **`ml_classifier` (`algorithm="tfidf"`) still falls back to a pre-trained baseline.** In [0035-merge-quick-screen-into-ml-filter](../0035-merge-quick-screen-into-ml-filter/spec.md), `ml_classifier` with `algorithm="tfidf"` was allowed to score prompts using the bundled pre-trained TF-IDF baseline (`_score_tfidf_baseline` / `load_baseline()`) whenever no custom dataset was provided. That contradicts the strict player-configured gameplay model ([0029-strict-win-lose-and-tool-config](../0029-strict-win-lose-and-tool-config/spec.md)) and misleads players in `/game`, which displays `"Using pre-trained TF-IDF baseline (or train on custom CSV)"`.
2. **`_fit_custom_pipeline` and the `/game` CSV draft still ship a default fallback dataset.** If `dataset` is omitted or has fewer than 2 rows in `_fit_custom_pipeline`, it falls back to `_DEFAULT_ML_DATASET`; and in `/game`, `mlCsvDraft` pre-populates sample rows instead of starting blank with a format placeholder.

## Goals

- Remove the pre-trained TF-IDF baseline fallback from `ml_classifier` evaluation: **every** `MLAlgorithmKind` (including `"tfidf"`) routes all prompts to `safe` (`"Model not trained"`) until the player supplies a valid 2-class training `dataset` (`>= 2` rows covering both `0` and `1` labels).
- Remove the `_DEFAULT_ML_DATASET` fallback from `_fit_custom_pipeline` / `train_custom_classifier`, raising `BoardValidationError` when fewer than 2 valid rows or fewer than 2 classes are provided.
- Update `/game` UI (`apps/web/app/pages/game.vue`) and `CHECK_CATALOG` summary so `ML filter` shows `"Not trained yet"` (or `"<N> rows trained"` / training accuracy once trained), removes all `"pre-trained TF-IDF baseline"` copy, and starts `mlCsvDraft` empty with a placeholder.

## Non-goals

- Removing `ClassifierDetector` or the bundled baseline artifact (`packages/engine/src/shield_engine/models/baseline/`) or `mise run train` (`test_baseline.py` and `test_classifier.py` remain intact for the library's standalone `ClassifierDetector`).
- Changing `ml_classifier` thresholds (`safe_threshold`, `block_threshold`), output handles (`safe`, `suspicious`), or 3-way routing logic once trained on user data.

## Behaviour

- **Untrained `ml_classifier` (all algorithms including `tfidf`):**
  - When `config.dataset` is missing, empty, has `< 2` rows, or has `< 2` distinct label classes (`0` and `1`), `evaluate_message` routes every prompt to `handle = "safe"` with `detail = "Model not trained"` (no call to `load_baseline()` or `_score_tfidf_baseline()`).
- **Trained `ml_classifier` (user-defined `dataset`):**
  - When `config.dataset` has `>= 2` rows covering both `0` and `1`, `evaluate_message` fits the selected scikit-learn pipeline (`tfidf`, `logistic_regression`, `linear_svm`, `naive_bayes`, or `random_forest`) on the user-supplied `dataset` and routes `proba <= safe_threshold` to `safe`, `proba >= block_threshold` to `block`, and `safe_threshold < proba < block_threshold` to `suspicious`.
- **`train_custom_classifier` / `POST /api/v1/game/train`:**
  - Rejects empty or missing `dataset` / `csv_text` (`< 2` rows or `< 2` classes) with `BoardValidationError` (`422` over HTTP) instead of falling back to `_DEFAULT_ML_DATASET`.
- **Web client (`/game`):**
  - `ML filter` settings modal displays `"Not trained yet"` when no dataset has been trained (never `"Using pre-trained TF-IDF baseline (or train on custom CSV)"`), updates the `Training data` tooltip to remove pre-trained baseline wording, and starts `mlCsvDraft` empty with a CSV format placeholder.

## Acceptance criteria

- **ENG-ML-003**: Given an `ml_classifier` node with `algorithm="tfidf"` (or any allowlisted algorithm) and no user-supplied `dataset`, when `evaluate_message` evaluates an attack or benign prompt, then it routes to `safe` with `"Model not trained"` without using the pre-trained baseline; and given `train_custom_classifier` with no dataset/CSV, it raises `BoardValidationError`. When the node's `model_id` refers to a model the player trained on their own 2-class rows, `algorithm="tfidf"` routes `safe`, `suspicious`, and `block` using only that user-trained model (no `config.dataset`; see [spec 0045](../0045-train-upload-hardening/spec.md)).
- **API-ML-002**: Given `POST /api/v1/game/run` with an untrained `ml_classifier` (`algorithm="tfidf"`, no trained `model_id`) on `easy`, when evaluated, then attacks are not blocked by a pre-trained baseline (`won=False`); and given `POST /api/v1/game/train` with empty `csv_text` or missing `dataset`, it returns `422` (training rules: [spec 0045](../0045-train-upload-hardening/spec.md)).
- **WEB-ML-002**: Given `/game` (`apps/web/app/pages/game.vue`), when opening the `ML filter` settings modal before training, then it displays `"Not trained yet"` (with no `"pre-trained"` or `"TF-IDF baseline"` wording) and starts `mlCsvDraft` empty with a CSV placeholder.

## Security & privacy considerations

- Removing implicit pre-trained fallback prevents players from accidentally passing levels with an unconfigured `ML filter` node and keeps training behavior explicit and transparent.

## Evaluation impact

- `ENG-ML-002` (from Spec 0035) is superseded by `ENG-ML-003`; existing tests that previously relied on an unconfigured `algorithm="tfidf"` node running the pre-trained baseline (`ENG-GAME-006`, `ENG-AGENT-002`, `API-GAME-002`) will supply explicit user `dataset` rows when testing `ml_classifier` routing.

## Open questions

- None.

## Verification

### 2026-11-19 · commit 2a0b84f (+ uncommitted changes)

- Criteria: ENG-ML-003, API-ML-002, WEB-ML-002
- Red: 3 failing test(s) before implementation (`packages/engine/tests/test_game.py::test_ml_classifier_uses_only_user_defined_dataset_never_pretrained_baseline`, `apps/api/tests/test_game_api.py::test_untrained_tfidf_does_not_block_and_train_rejects_empty_data`, `design hygiene and anti-slop copy standard [WEB-ML-002] removes pre-trained TF-IDF baseline wording and starts mlCsvDraft empty with a placeholder`)
- Green: 3 passing test(s)
- Gate: `mise run check` passed
