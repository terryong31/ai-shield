# 0029 — Strict win/lose and tool configuration

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-17
- **Related:** [0016-game-engine](../0016-game-engine/spec.md), [0020-game-ai-agent](../0020-game-ai-agent/spec.md), [0021-game-level-tiers](../0021-game-level-tiers/spec.md)

## Problem

1. **Preset-based tools trivialise levels.** `word_filter` ships with three built-in rule-set presets (`Overrides`, `Encoded`, `SQL and tools`) all enabled by default. Because those presets contain the exact attack phrases used in Level 1 (and many in Levels 2–3), a player can drop a single unconfigured `word_filter` node and immediately win Level 1 with a Gold medal. Similarly, `ml_classifier` falls back to a pre-seeded `_DEFAULT_ML_DATASET` containing the level's exact attack phrases, and `secret_scan` / `tool_filter` rely on hidden hardcoded lists with no player configuration.
2. **Lenient win/lose and non-efficiency scoring.** Currently `score_wave` awards up to 8,000+ points even when attacks leak, and grants a `bronze` medal with `attacks_leaked == 1`. A single leaked attack should be an immediate **Loss**, and winning should be scored strictly on workflow efficiency (latency, cost, tokens, and tool accuracy).

## Goals

- Remove built-in presets from `word_filter` and require players to inspect level threats and configure checks (`custom_words`, `secret_scan` patterns, `tool_filter` blocked tools, `ml_classifier` training data, `length_limit`, `quick_screen` thresholds).
- Enforce a strict zero-leak, zero-false-alarm Win/Lose rule: any leaked attack (`attacks_leaked >= 1`) or blocked/refused benign prompt (`false_alarms >= 1`) results in a **Loss** (`won = False`, `total_score = 0`, `medal = "none"`).
- Score **Winning** runs (`won = True`) strictly on efficiency: speed (latency), cost, token usage, and tool accuracy.

## Non-goals

- Changing the graph wiring model (`incoming`, `assistant`, `safe`/`suspicious`/`out`/`done` handles).
- Changing `safety_check` or `agent_review` pricing/latency or adding new node types.
- Migrating or invalidating historical leaderboard scores stored prior to this change (new runs use the new scoring).

## Behaviour

### Tool configuration

| Tool (`kind`) | Default behaviour when unconfigured | Required player configuration |
| --- | --- | --- |
| `word_filter` | Blocks nothing (`safe` for all) | `custom_words`: list of blocked phrases (case-insensitive substring match) |
| `ml_classifier` | Blocks nothing (`safe` for all, 0% risk) | `dataset`: player-supplied training rows (≥ 1 attack and ≥ 1 benign) + `threshold` |
| `secret_scan` | Blocks nothing (`safe` for all) | `patterns`: list of secret/keyword patterns to guard |
| `tool_filter` | Blocks nothing (`safe` for all) | `blocked_tools`: list of restricted tool/SQL names to block |
| `length_limit` | Blocks `len(text) > 240` | `max_chars` |
| `quick_screen` | Pretrained baseline (`0.30` / `0.75`) | `safe_threshold`, `block_threshold`, and wiring `safe` / `suspicious` |
| `text_cleanup` | Strips zero-width chars, unpacks base64 | Placement in pipeline |
| `safety_check` | Detects roleplay/jailbreak (`85ms`, `$0.0002`) | Model selection & cost-aware placement (e.g. on `suspicious` branch) |
| `agent_review` | Deep review (`920ms`, `$0.0030`) | Model selection & cost-aware placement |

Legacy saved boards that contain `word_filter` `config.groups` continue to validate without error, but `groups` is ignored and only `custom_words` is evaluated.

### Win / Lose & Scoring

- **Win condition**: `won = (attacks_leaked == 0 and false_alarms == 0)` (when `attacks_total > 0` or `benign_total > 0`).
- **Loss**: If `not won`:
  - `total_score = 0`
  - `medal = "none"`
  - `protection_points = helpfulness_points = tool_points = token_points = speed_points = cost_points = 0`
  - Diagnostic fields (`attacks_protected`, `attacks_leaked`, `benign_helped`, `false_alarms`, `avg_latency_ms`, `total_cost_usd`, `total_tokens`) are still returned.
- **Win scoring (`0..10,000`)**:
  - Classification-only levels (`classify_only=True`):
    - `speed_points` (max `5000`): linear from `5000` at `0ms` to `0` at `max_latency_ms`
    - `cost_points` (max `5000`): linear from `5000` at `$0` to `0` at `max_cost_usd`
  - Agent levels (`classify_only=False`):
    - `speed_points` (max `3500`): linear from `3500` at `0ms` to `0` at `max_latency_ms`
    - `cost_points` (max `3500`): linear from `3500` at `$0` to `0` at `max_cost_usd`
    - `token_points` (max `2000`): linear from `2000` at `0` tokens to `0` at `token_budget`
    - `tool_points` (max `1000`): `round(1000 * tool_hits / tool_expected)` (or `1000` if `tool_expected == 0`)
- **Medals on Win**:
  - `gold`: `won and total_score >= 8500`
  - `silver`: `won and total_score >= 7000`
  - `bronze`: `won and total_score < 7000`

## Acceptance criteria

- **ENG-TOOL-001**: Given a `word_filter` node with no `custom_words` (even if legacy `groups` is present in `config`), when an override, encoded, or SQL attack prompt is evaluated, then `word_filter` routes it to `safe` and does not block it.
- **ENG-TOOL-002**: Given a `word_filter` node with `custom_words` containing `"ignore previous instructions"`, when a matching prompt is evaluated, then `word_filter` blocks it and records the matched phrase.
- **ENG-TOOL-003**: Given an `ml_classifier` node with no player-supplied `dataset`, when any prompt is evaluated, then `ml_classifier` routes it to `safe` without using a pre-seeded level-attack dataset.
- **ENG-TOOL-004**: Given a `secret_scan` node with no `patterns` configured, when a prompt containing `"password"` is evaluated, then `secret_scan` routes it to `safe`; when `patterns` includes `"password"`, then it blocks the prompt.
- **ENG-TOOL-005**: Given a `tool_filter` node with no `blocked_tools` configured, when a prompt containing `"export_payroll"` is evaluated, then `tool_filter` routes it to `safe`; when `blocked_tools` includes `"export_payroll"`, then it blocks the prompt. Replaced by ENG-FAIR-008 (0050).
- **ENG-SCORE-001**: Given a wave run where `attacks_leaked >= 1`, when `score_wave` computes the result, then `won` is `False`, `total_score` is `0`, and `medal` is `"none"`. Replaced by ENG-FAIR-001, ENG-FAIR-005 (0050).
- **ENG-SCORE-002**: Given a wave run where `attacks_leaked == 0` and `false_alarms >= 1`, when `score_wave` computes the result, then `won` is `False`, `total_score` is `0`, and `medal` is `"none"`. Replaced by ENG-FAIR-001, ENG-FAIR-005 (0050).
- **ENG-SCORE-003**: Given a winning wave run (`attacks_leaked == 0` and `false_alarms == 0`), when `score_wave` computes the result, then `won` is `True`, `total_score` is computed strictly from speed, cost, token efficiency, and tool accuracy, and `medal` is `"gold"` (`>= 8500`), `"silver"` (`>= 7000`), or `"bronze"` (`< 7000`). Replaced by ENG-FAIR-001, ENG-FAIR-002 (0050).
- **API-GAME-001**: Given a completed wave response from `/api/v1/game/waves` or `/api/v1/game/sandbox/run`, when serialized to JSON, then `score.won` is a boolean matching `WaveScore.won` and OpenAPI contract + generated web types include `won`.
- **WEB-GAME-001**: Given the `word_filter` configuration modal in `/game`, when opened, then no preset "Rule sets" buttons are rendered and only "Custom blocked words" is shown.
- **WEB-GAME-002**: Given a wave result in `/game` where `won` is `False`, when the Run results modal is displayed, then it clearly indicates a Loss (with 0 stars, score `0`, and reason such as leaked attacks or false alarms). Replaced by WEB-FAIR-001 (0050).

## Security & privacy considerations

- Removing hardcoded attack-phrase presets from `word_filter` and `_DEFAULT_ML_DATASET` from `ml_classifier` does not expose any secrets or weaken `wrap_untrusted()` boundaries.
- Zero-tolerance scoring ensures leaked prompts never yield a passing medal.

## Evaluation impact

- Engine game scoring weights shift from protection/helpfulness points (pass/fail gate) to pure efficiency points (`speed`, `cost`, `tokens`, `tools`).
- **Before vs After reference scores**:
  - Unconfigured single `word_filter` on Easy: **Before** `10,000` (`gold`, 4/4 attacks blocked by built-in `override` preset) -> **After** `0` (`none`, `won=False`, 4/4 attacks leaked).
  - Configured `word_filter` (`custom_words` covering level overrides) on Easy: **Before** `10,000` (`gold`) -> **After** `9,999` (`gold`, `won=True`, `speed_points=4999`, `cost_points=5000`).
  - Run with 1 leaked attack and 1 false alarm on Medium: **Before** `6,325` (`bronze`) -> **After** `0` (`none`, `won=False`).
  - Winning cascading board (`text_cleanup -> quick_screen -> agent_review`) vs all-`agent_review` board on Medium: **Before** `9,731` vs `9,108` -> **After** `9,041` (`gold`) vs `5,952` (`bronze`), making the latency/cost penalty of overusing heavy LLM checks decisive.

## Open questions

- None.

## Verification

### 2026-11-17 · commit 2a0b84f (+ uncommitted changes)

- Criteria: ENG-TOOL-001, ENG-TOOL-002, ENG-TOOL-003, ENG-TOOL-004, ENG-TOOL-005, ENG-SCORE-001, ENG-SCORE-002, ENG-SCORE-003, API-GAME-001, WEB-GAME-001, WEB-GAME-002
- Red: 11 failing test(s) before implementation (`packages/engine/tests/test_game.py::test_word_filter_without_custom_words_passes_attacks_and_ignores_legacy_groups`, `packages/engine/tests/test_game.py::test_word_filter_with_custom_words_blocks_matching_prompts`, `packages/engine/tests/test_game.py::test_ml_classifier_without_player_dataset_passes_prompts_untrained`)
- Green: 14 passing test(s)
- Gate: `mise run check` passed
