# Plan — 0029 Strict win/lose and tool configuration

## Engine (`packages/engine`)

1. **`packages/engine/src/shield_engine/game/__init__.py`**:
   - Add `won: bool` to `WaveScore`.
   - Update `WordFilterDetector` / `word_filter` evaluation: remove `_RULE_GROUPS` preset matching; evaluate only `custom_words`.
   - Update `ml_classifier` evaluation: if `dataset` is missing or has fewer than 2 classes (benign + attack), do not fall back to `_DEFAULT_ML_DATASET` — return `safe` with `"Not trained"` detail.
   - Update `secret_scan` evaluation: read `node.config.get("patterns", [])` (case-insensitive substring match); if empty, return `safe`.
   - Update `tool_filter` evaluation: read `node.config.get("blocked_tools", [])` (case-insensitive substring match); if empty, return `safe`.
   - Update `score_wave`:
     - `won = attacks_leaked == 0 and false_alarms == 0`
     - On loss (`not won`): `total_score = 0`, `medal = "none"`, all component points `0`.
     - On win (`won`): compute `speed_points`, `cost_points`, `token_points`, `tool_points` using the efficiency weights (`5000/5000` for classify-only; `3500/3500/2000/1000` for agent levels), and assign `gold` / `silver` / `bronze`.

## API (`apps/api`)

2. **`apps/api/src/shield_api/schemas.py`** & **`apps/api/src/shield_api/routers/game.py`**:
   - Add `won: bool` to `WaveScoreSchema` and pass `score.won` in `_score_to_schema`.
   - Run `mise run contract` to regenerate `contracts/openapi.json` and `apps/web/app/types/api.gen.ts`.

## Web (`apps/web`)

3. **`apps/web/app/pages/game.vue`** & **`apps/web/app/utils/gameBoard.ts`**:
   - Remove the `Rule sets` preset buttons and helpers (`hasRuleGroup`, `toggleRuleGroup`) from `word_filter` modal; keep `Custom blocked words`.
   - Add pattern list configuration UI for `secret_scan` (`patterns`) and `tool_filter` (`blocked_tools`), reusing the same clean chip/list input pattern.
   - Start `ml_classifier` with empty dataset until the user enters/uploads CSV and clicks `Train model`.
   - Update Run results & Score breakdown modals to display `Won` vs `Lost` badge/reason and efficiency breakdown.
