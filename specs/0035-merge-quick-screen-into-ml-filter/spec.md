# 0035 — Merge Quick screen into ML filter with TF-IDF and Unclear output

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-17
- **Related:** [0016-game-engine](../0016-game-engine/spec.md), [0020-game-ai-agent](../0020-game-ai-agent/spec.md)

## Problem

`Quick screen` (`quick_screen`) and `ML filter` (`ml_classifier`) duplicate ML text classification on `/game`:
- `Quick screen` wraps the repo's pre-trained TF-IDF + SGD baseline classifier (`ClassifierDetector`) with two thresholds (`safe_threshold`, `block_threshold`) and two output ports (`safe` / `pass` and `suspicious` / `unclear`).
- `ML filter` trains custom scikit-learn classifiers (`logistic_regression`, `linear_svm`, `naive_bayes`, `random_forest`) from CSV data, has no pre-trained TF-IDF option, and only exposes a single binary `threshold` with a single `safe` (`pass`) output port, leaving players unable to route semi-confident ML scores (`safe_threshold < score < block_threshold`) to downstream checks.

## Goals

- Remove `quick_screen` completely from the engine catalog, board validation, HTTP schema/contract, and `/game` web UI.
- Add `tfidf` (TF-IDF + SGD, backed by the bundled pre-trained baseline when no custom CSV dataset is uploaded) as an algorithm inside `ml_classifier`.
- Give `ml_classifier` the two thresholds (`safe_threshold` "Pass below", default `0.30`; `block_threshold` "Block at or above", default `0.75`) and two output ports (`safe` / `pass`, `suspicious` / `unclear`) so players can wire semi-confident predictions to downstream nodes.
- Update prior `Implemented` specs/tests that asserted `quick_screen` (`ENG-GAME-006`, `API-GAME-001`, `ENG-AGENT-011`, `WEB-AGENT-012`) to reflect its retirement into `ml_classifier`.

## Non-goals

- Removing the bundled baseline classifier artifact (`packages/engine/src/shield_engine/models/baseline/`) or `mise run train`; it now powers `ml_classifier` when `algorithm="tfidf"` is used without custom training data.
- Changing scoring formulas, win/lose rules, or strict zero-leak rules.

## Behaviour

### 1. Retire `quick_screen`

- `quick_screen` is removed from `NodeKind`, `VALID_NODE_KINDS`, `CHECK_CATALOG`, `NODE_CATALOG`, and `/game` Tools palette & node settings modal.
- `validate_board` raises `BoardValidationError` if a board contains `kind="quick_screen"`.
- On the web client, [`boardFromSave`](apps/web/app/utils/gameBoard.ts) treats saved boards containing `quick_screen` as incompatible and resets to the level's starter board.

### 2. TF-IDF and 3-way routing inside `ml_classifier`

- `ml_classifier` (`ML filter`) exposes `handles=("safe", "suspicious")` (displayed on the node as `pass` and `unclear`).
- `ALLOWED_ML_ALGORITHMS` becomes:
  - `"tfidf"` (`TF-IDF`) — default algorithm on newly created `ml_classifier` nodes.
    - When `config.dataset` has `< 2` valid rows or `< 2` label classes, `ml_classifier` evaluates `working_text` using the bundled pre-trained TF-IDF baseline classifier (with the existing keyword floors).
    - When `config.dataset` has a valid 2-class training dataset, it fits `TfidfVectorizer(ngram_range=(1, 2))` + `SGDClassifier(loss="log_loss")` on the uploaded dataset.
  - `"logistic_regression"`, `"linear_svm"`, `"naive_bayes"`, `"random_forest"` — pass to `safe` (`"Model not trained"`) until trained with 2-class CSV data, as today.
- Thresholds:
  - `safe_threshold`: `"Pass below"` (`0.00` to `block_threshold - 0.05`, default `0.30`).
  - `block_threshold`: `"Block at or above"` (`safe_threshold + 0.05` to `1.00`, default `0.75`).
  - Routing for predicted risk probability `proba`:
    - `proba >= block_t` -> `"block"` (stops immediately).
    - `proba <= safe_t` -> `"safe"` (`pass` output port).
    - `safe_t < proba < block_t` -> `"suspicious"` (`unclear` output port).
  - Legacy single-threshold configs containing `threshold` without `safe_threshold`/`block_threshold` treat both cutoffs as `float(config["threshold"])` so existing single-threshold saves behave identically until edited.
  - `validate_board` raises `BoardValidationError` if `safe_threshold >= block_threshold` or either is outside `[0.0, 1.0]`.

## Acceptance criteria

- **ENG-ML-001**: Given a board with `kind="quick_screen"`, when `validate_board` or `get_check_catalog` runs, then `quick_screen` is rejected with `BoardValidationError` and absent from `CHECK_CATALOG`.
- **ENG-ML-002**: Given an `ml_classifier` node with `algorithm="tfidf"` and no custom dataset, when evaluated, then it scores prompts with the bundled TF-IDF baseline and routes `proba <= safe_threshold` to `safe`, `proba >= block_threshold` to `block`, and `safe_threshold < proba < block_threshold` to `suspicious` (`unclear`).
- **API-ML-001**: Given `GET /api/v1/game/levels`, when called, then `checks` omits `quick_screen` and lists `ml_classifier` with `handles: ["safe", "suspicious"]`; `POST /api/v1/game/train-ml` accepts `algorithm="tfidf"` on custom CSV data.
- **WEB-ML-001**: Given `/game`, when inspecting the Tools panel, `NODE_CATALOG`, and `ML filter` settings modal, then `quick_screen` is absent, `ml_classifier` has `handles: ['safe', 'suspicious']`, the algorithm `<USelectMenu>` includes `TF-IDF`, and both `Pass below` (`safe_threshold`) and `Block at or above` (`block_threshold`) `<UInputNumber>` controls are editable.

## Security & privacy considerations

- Retains hash-verified loading (`load_baseline()`) for the bundled TF-IDF baseline when `algorithm="tfidf"` runs without custom CSV data.
- Rejects invalid threshold ranges (`safe_threshold >= block_threshold`) in `validate_board` to prevent ambiguous routing.

## Evaluation impact

- Re-run `mise run test:engine` and note updated `ENG-GAME-006` medium-level cascading score using `ml_classifier` (`algorithm="tfidf"`).

## Open questions

- None (pending human review and acceptance of removing `quick_screen` across legacy criteria `ENG-GAME-006`, `API-GAME-001`, `ENG-AGENT-011`, `WEB-AGENT-012`).

## Verification

### 2026-11-17 · commit 2a0b84f (+ uncommitted changes)

- Criteria: ENG-ML-001, ENG-ML-002, API-ML-001, WEB-ML-001
- Red: 4 failing test(s) before implementation (`packages/engine/tests/test_game.py::test_quick_screen_removed_from_catalog_and_rejected_by_validate_board`, `packages/engine/tests/test_game.py::test_ml_classifier_tfidf_routes_safe_suspicious_and_block`, `apps/api/tests/test_game_api.py::test_levels_catalog_omits_quick_screen_and_train_accepts_tfidf`)
- Green: 4 passing test(s)
- Gate: `mise run check` passed

### 2026-11-17 · commit 2a0b84f (+ uncommitted changes)

- Criteria: API-ML-001
- Red: 1 failing test(s) before implementation (`apps/api/tests/test_game_saves_api.py::test_get_saved_board_migrates_legacy_quick_screen_to_ml_classifier`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed
