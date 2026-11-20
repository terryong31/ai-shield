# Tasks — 0029 Strict win/lose and tool configuration

- [x] Human review & mark `specs/0029-strict-win-lose-and-tool-config/spec.md` as `Accepted`
- [x] `mise run sdd:start 0029`
- [x] **ENG-TOOL-001** `word_filter` with no `custom_words` passes all prompts and ignores legacy `groups`
- [x] **ENG-TOOL-002** `word_filter` blocks prompts matching configured `custom_words`
- [x] **ENG-TOOL-003** `ml_classifier` with no player-supplied `dataset` routes prompts to `safe` without pre-seeded level data
- [x] **ENG-TOOL-004** `secret_scan` requires configured `patterns` to block
- [x] **ENG-TOOL-005** `tool_filter` requires configured `blocked_tools` to block
- [x] **ENG-SCORE-001** `score_wave` sets `won=False`, `total_score=0`, `medal="none"` when `attacks_leaked >= 1`
- [x] **ENG-SCORE-002** `score_wave` sets `won=False`, `total_score=0`, `medal="none"` when `false_alarms >= 1`
- [x] **ENG-SCORE-003** `score_wave` sets `won=True` and computes `total_score` and `medal` strictly from efficiency when `attacks_leaked == 0` and `false_alarms == 0`
- [x] **API-GAME-001** Expose `score.won` boolean in `WaveScoreSchema` and regenerate OpenAPI contract + web types
- [x] **WEB-GAME-001** Remove preset `Rule sets` buttons from `word_filter` modal in `/game`
- [x] **WEB-GAME-002** Show explicit Win/Loss state and failure reason in Run results modal in `/game`
