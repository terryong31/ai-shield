# 0038 — ML filter user-defined training data only: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

1. **Engine (`packages/engine/src/shield_engine/game/__init__.py`)**:
   - Update `CHECK_CATALOG` entry for `ml_classifier` summary to `"Trainable ML classifier with Safe, Unclear, and Block branches."`.
   - Remove `_DEFAULT_ML_DATASET`, `_cached_baseline()`, and `_score_tfidf_baseline()` fallback from `shield_engine/game/__init__.py`.
   - In `_fit_custom_pipeline`, require `dataset` with at least 2 rows and both classes (`0` and `1`), raising `BoardValidationError("Dataset must contain at least 2 rows with text and label.")` when missing/too small.
   - In `evaluate_message` (`elif node.kind == "ml_classifier":`), remove the `elif algo == "tfidf":` pre-trained baseline branch so untrained `tfidf` nodes fall into `else: handle = "safe"; detail = "Model not trained"`, matching every other algorithm.

2. **Web UI (`apps/web/app/pages/game.vue`)**:
   - Change `mlCsvDraft` to `ref('')` and add a CSV format `placeholder` on the `<UTextarea>` in the `ML filter` `Training data` section.
   - Remove `"TF-IDF runs the pre-trained baseline out of the box if left untrained."` from the `Training data` `<UTooltip>`.
   - Replace `'Using pre-trained TF-IDF baseline (or train on custom CSV)'` with `(Array.isArray(selectedNode.data.config.dataset) && selectedNode.data.config.dataset.length >= 2) ? \`\${selectedNode.data.config.dataset.length} rows trained\` : 'Not trained yet'`.

3. **Tests & Specs**:
   - Update `ENG-ML-002` / `ENG-GAME-006` in `packages/engine/tests/test_game.py`, `ENG-AGENT-002` in `packages/engine/tests/test_game_agent.py`, and `API-GAME-002` in `apps/api/tests/test_game_api.py` to supply explicit `dataset` rows on `ml_classifier` boards where routing is expected.
   - Add criteria tests for `ENG-ML-003`, `API-ML-002`, and `WEB-ML-002`.
   - Update `docs/reference/engine-api.md` and `CHANGELOG.md`.

## Interfaces

- No HTTP schema or public function signature changes.

## Boundaries check

- [ ] `packages/engine` remains free of web frameworks, databases, and `shield_api`.
- [ ] `apps/web` still talks to the gateway only through `useShieldApi()` and `api.gen.ts`.
- [ ] Reference docs in `docs/reference/engine-api.md` reflect the change.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Only change the UI label while keeping `_score_tfidf_baseline` in the engine | Would leave `algorithm="tfidf"` secretly scoring with the pre-trained baseline behind the scenes, contradicting "do not use pre-trained, use only user pre defined data". |

## Risks and rollback

- Existing saved boards with `ml_classifier` (`algorithm="tfidf"`) and no `dataset` will safely route to `safe` (`"Model not trained"`) until the player trains them with CSV data.
