# 0035 — Merge Quick screen into ML filter: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

1. **Engine (`packages/engine/src/shield_engine/game/__init__.py`)**:
   - Remove `"quick_screen"` from `NodeKind`, `VALID_NODE_KINDS`, `CHECK_CATALOG`, and `evaluate_message`.
   - Add `"tfidf"` to `MLAlgorithmKind` / `ALLOWED_ML_ALGORITHMS` and support it in `_build_sklearn_pipeline` (`SGDClassifier(loss="log_loss", max_iter=200, random_state=42)`).
   - Update `ml_classifier` `CheckDefinition` to `handles=("safe", "suspicious")` and update `validate_board` to validate `safe_threshold` / `block_threshold` on `ml_classifier`.
   - Rename `_score_quick_screen` to `_score_tfidf_baseline` and invoke it in `ml_classifier` evaluation when `algorithm == "tfidf"` and no valid 2-class `dataset` is attached; otherwise compute `proba` from the fitted custom pipeline and route `<= safe_threshold` -> `"safe"`, `>= block_threshold` -> `"block"`, else -> `"suspicious"`.
2. **API & Contract (`apps/api`, `contracts/`)**:
   - Export updated OpenAPI schema & generated web types via `mise run contract` (`quick_screen` removed from `NodeKind` enum; `ml_classifier` handles updated).
3. **Web (`apps/web/app/utils/gameBoard.ts`, `apps/web/app/pages/game.vue`)**:
   - Remove `quick_screen` from `NODE_CATALOG`, `makeGameNode`, `toApiBoard` fallback (`ml_classifier`), `game.vue` tool groups, and its modal section.
   - Update `ml_classifier` in `NODE_CATALOG` to `handles: ['safe', 'suspicious']` and `makeGameNode('ml_classifier')` defaults (`algorithm: 'tfidf'`, `safe_threshold: 0.3`, `block_threshold: 0.75`, `dataset: []`).
   - Add `{ id: 'tfidf', label: 'TF-IDF (Baseline)' }` to `mlAlgorithms` and replace the single `threshold` `UInputNumber` with `Pass below` (`safe_threshold`) and `Block at or above` (`block_threshold`) `UInputNumber` controls (mirroring the retired Quick screen UI cleanly).

## Interfaces

```python
MLAlgorithmKind = Literal[
    "tfidf",
    "logistic_regression",
    "linear_svm",
    "naive_bayes",
    "random_forest",
]
```

**Breaking change:** `quick_screen` is removed from `NodeKind` in engine and OpenAPI schema.

## Boundaries check

- [ ] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [ ] `apps/web` still talks to the backend only through the published OpenAPI contract
- [ ] New configuration is documented in `docs/reference/` and `MODEL_CARD.md`

## Alternatives considered

| Option | Why not |
| --- | --- |
| Keep `quick_screen` as a hidden backend alias | Leaves dead code and duplicate classifier semantics in the public API; owner requested removing `quick_screen` entirely. |

## Risks and rollback

- Previously saved user boards containing `quick_screen` will be reset to the starter board by `boardFromSave` because `quick_screen` is no longer in `NODE_CATALOG`.
- Existing `Implemented` spec tests (`ENG-GAME-006`, `API-GAME-001`, `ENG-AGENT-011`, `WEB-AGENT-012`) must be updated with human sign-off to reference `ml_classifier` instead of `quick_screen`.
