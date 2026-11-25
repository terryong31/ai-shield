# 0039 — Campaign levels and difficulty leaderboard

- **Status:** Implemented
- **Area:** ENG | API
- **Owner:** Terry Ong
- **Created:** 2026-11-19
- **Related:** [0016-game-engine](../0016-game-engine/spec.md), [0021-game-level-tiers](../0021-game-level-tiers/spec.md), [0024-domain-schema-storage](../0024-domain-schema-storage/spec.md), [0029-strict-win-lose-and-tool-config](../0029-strict-win-lose-and-tool-config/spec.md), [0037-langgraph-agent-and-tool-policy](../0037-langgraph-agent-and-tool-policy/spec.md), [0038-ml-classifier-user-data-only](../0038-ml-classifier-user-data-only/spec.md), [0040-campaign-problem-hub-and-briefing-ui](../0040-campaign-problem-hub-and-briefing-ui/spec.md)

## Problem

1. **Three static levels are too short for a commercial game.** Today `ai-shield` ships only `easy`, `medium`, and `hard` as single levels. Once a player clears three waves, there is no campaign progression, no puzzle variety, and minimal replay value to justify a paid subscription.
2. **Tools are strictly static (`allowed=True` or `allowed=False`).** Real AI agents use dual-purpose tools that are legitimate in one customer conversation and dangerous when baited in another. Without conditional Dual-Use tools, architectural constraints, and optional Follow-Up mastery goals, players do not need selective Tool Policy routing across varied security architectures.
3. **High scores are isolated per single level.** `game.scores` only ranks single-level runs and has no difficulty-category aggregation, so there is no total high score across all levels within `Easy`, `Medium`, or `Hard`. Legacy `easy`, `medium`, and `hard` scores and saved boards also sit in `game.scores` and `game.saved_boards` on an incompatible level taxonomy.

## Goals

- Turn `Easy`, `Medium`, and `Hard` into difficulty categories containing **23 unique levels** total:
  - **Easy (5 levels — 3 Free `easy-1..easy-3`, 2 Pro `easy-4..easy-5`)**: Classification-only (`agent=None`, no LLM agent).
  - **Medium (10 levels — 2 Free `medium-1..medium-2`, 8 Pro `medium-3..medium-10`)**: Real LangGraph `standard`-tier agent, 2–4 tools.
  - **Hard (8 levels — 0 Free, 8 Pro `hard-1..hard-8`)**: Real LangGraph `budget` (gullible)-tier agent, 4–6 tools.
- Add per-level **Hard Constraints** (`max_check_nodes`, `disabled_checks`, `max_avg_latency_ms`, `max_total_cost_usd`, `max_tokens`) and per-level **Follow-Up Challenges** (`follow_up_passed`, `follow_up_feedback`) evaluated on the same single wave run with zero extra LLM calls.
- Add **Dual-Use (Conditional) Tools** (`AgentTool.dual_use: bool = False`, `LevelMessage.forbidden_tools: tuple[str, ...] = ()`) so a tool can be legitimately required on some benign prompts and forbidden on baited or attack prompts in the same wave.
- Enforce **Pro-tier level gating** (`403`) on `POST /api/v1/game/run` and `/api/v1/game/saves/{level_id}` when an `anonymous` or `free` player attempts a `pro` level.
- Apply a new Supabase migration (mirrored in SQLite stores per `API-SCHEMA-006`) adding `won` and `mastered` columns to `game.scores`, purging legacy scores and `easy`/`medium`/`hard` saved boards, and bumping `SCORE_VERSION` to `3`.
- Calculate difficulty-category high scores as the **sum of each player's best scores across all levels in that difficulty** via `GET /api/v1/game/leaderboard`, plus `GET /api/v1/game/progress` for the signed-in player's per-level status and per-difficulty totals.
- Keep `apps/web` type-checked and green against the regenerated OpenAPI contract (`mise run contract`) with minimal compatibility wiring (the full LeetCode-style Problem Hub and in-game Briefing/Constraint/Follow-Up UI will be Spec `0040`).

## Non-goals

- Sample cases vs. hidden test suites (`Run` vs. `Submit`), excluded at MVP to keep server LLM costs predictable.
- Percentile benchmarks (`Beats X%`), deferred to a future analytics spec.
- Full LeetCode-style Problem Hub redesign on `/` and in-game Mission Briefing, locked palette nodes, and Solved/Mastered celebration UI (scoped to Spec `0040`).

## Behaviour

### 1. Campaign Types and 23-Level Taxonomy

`shield_engine.game` replaces the 3 fixed level literals with difficulty categories and 23 unique level slugs:

- `DifficultyCategory = Literal["Easy", "Medium", "Hard"]`
- `LevelTier = Literal["free", "pro"]`
- `LevelId`: literal union of `"easy-1"`..`"easy-5"`, `"medium-1"`..`"medium-10"`, and `"hard-1"`..`"hard-8"`.
- `ALL_LEVEL_IDS: tuple[LevelId, ...]` lists all 23 slugs in progression order; `LEVEL_IDS_BY_DIFFICULTY: dict[DifficultyCategory, tuple[LevelId, ...]]` groups them by `Easy` (5), `Medium` (10), and `Hard` (8).
- `LevelConstraints` (frozen dataclass): `max_check_nodes: int | None = None`, `disabled_checks: tuple[NodeKind, ...] = ()`, `max_avg_latency_ms: float | None = None`, `max_total_cost_usd: float | None = None`, `max_tokens: int | None = None`.
- `FollowUpChallenge` (frozen dataclass): `description: str`, `max_check_nodes: int | None = None`, `forbidden_checks: tuple[NodeKind, ...] = ()`, `max_avg_latency_ms: float | None = None`, `max_total_cost_usd: float | None = None`, `max_tokens: int | None = None`.
- `AgentTool` adds `dual_use: bool = False`. A tool with `allowed=True` and `dual_use=True` is conditional (safe when required, forbidden when baited/attacked).
- `LevelMessage` adds `forbidden_tools: tuple[str, ...] = ()`.
- `GameLevel` adds `order: int`, `tier: LevelTier`, `tags: tuple[str, ...]`, `constraints: LevelConstraints`, and `follow_up: FollowUpChallenge | None`.
- `WaveScore` adds `constraint_violations: tuple[str, ...] = ()`, `follow_up_passed: bool = False`, and `follow_up_feedback: str = ""`.

#### Easy — 5 Levels (Classification-Only, `agent=None`, 8–10 prompts each)

| ID | Order | Tier | Title | Core Puzzle & Concept Tags | Hard Constraint | Follow-Up Challenge (Mastery) |
| --- | --- | --- | --- | --- | --- | --- |
| `easy-1` | 1 | `free` | Public Helpdesk | Direct prompt overrides + oversized prompt stuffing (`Word Filter`, `Length Limit`, `Edge Defence`) | None | `<= 2` check nodes and avg latency `<= 1.0 ms` |
| `easy-2` | 2 | `free` | Hidden in Plain Sight | Zero-width characters, Base64, and hex/URL smuggling requiring `Text Cleaner` before `Secret Scanner` (`Text Cleaner`, `Secret Scan`, `Pipeline Order`) | None | `\$0.00` total cost (no paid AI checks) |
| `easy-3` | 3 | `free` | Train Your First Guard | Paraphrased social-engineering attacks blocked via custom CSV `ML Filter` and 3-way `Safe`/`Unclear` branching (`ML Filter`, `3-Way Branching`) | `word_filter` disabled | `\$0.00` total cost and avg latency `<= 6.0 ms` |
| `easy-4` | 4 | `pro` | Developer Docs Trap | Benign developers asking about `SELECT *` and `API_KEY` documentation vs. real credential theft (`False Positives`, `ML Triage`) | Max `4` check nodes | `\$0.00` total cost |
| `easy-5` | 5 | `pro` | The Noisy Gateway | Easy capstone mixing stuffing, nested encoding, paraphrased overrides, and benign lookalikes (`Capstone`, `Latency SLA`) | Avg latency `<= 8.0 ms` | `<= 4` check nodes and `\$0.00` total cost |

#### Medium — 10 Levels (Real LangGraph `standard` Agent, 2–4 tools, 10–12 prompts each)

| ID | Order | Tier | Title | Agent Tools (`R` = Restricted, `DU` = Dual-Use) | Core Puzzle Twist | Hard Constraint | Follow-Up Challenge (Mastery) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `medium-1` | 6 | `free` | HR Handbook Assistant | `search_handbook`, `read_salary_records` (R) | First LangGraph agent: Base64, roleplay, direct overrides + benign quick-fix/pasted bait | None | No `agent_review` |
| `medium-2` | 7 | `free` | Over-Helpful Refund Bot | `lookup_order`, `issue_refund` (R) | Pattern C quick-fix bait: let legitimate shoppers through while switching off Tool 2 (`issue_refund`) | None | Avg latency `<= 600.0 ms` |
| `medium-3` | 8 | `pro` | Poisoned Inbox | `summarize_thread`, `forward_external_email` (R) | Pattern D pasted RAG bait: forwarded vendor threads embed commands in quoted bodies | None | `<= 3` check nodes |
| `medium-4` | 9 | `pro` | Lost in Translation | `check_appointment`, `export_patient_records` (R) | Non-English (Malay/Spanish) and JSON-wrapped overrides that bypass naive keyword lists | `word_filter` disabled | Total cost `<= \$0.008` |
| `medium-5` | 10 | `pro` | Confused Dev Copilot | `search_docs`, `read_env_secrets` (R), `run_sql` (R) | Educational `.env` and SQL questions mixed with real secret-exfiltration attempts | None | `max_tokens <= 4500` |
| `medium-6` | 11 | `pro` | 50ms Express Lane | `check_exchange_rate`, `wire_transfer` (R) | Tiered funnel: route clear safe traffic around costly semantic checks to meet strict cost SLA | Total cost `<= \$0.005` | No `agent_review` |
| `medium-7` | 12 | `pro` | IT Helpdesk Triage | `search_kb`, `reset_mfa` (R), `grant_admin` (R), `delete_ticket` (R) | Multiple dangerous tools baited across tickets; dynamic `agent_review` or multi-branch `jev` Policy | Max `5` check nodes | `<= 3` check nodes |
| `medium-8` | 13 | `pro` | Dual-Use Refund Desk | `lookup_order`, `issue_store_credit` (DU), `export_pii` (R) | First Dual-Use tool: `issue_store_credit` is required for damaged items and forbidden on baited claims | None | No `agent_review` |
| `medium-9` | 14 | `pro` | Encoded Cargo Courier | `track_shipment`, `reroute_cargo` (R), `cancel_invoice` (R) | Tool baits smuggled inside Base64 tracking notes and URL-encoded links; clean before Tool Policy | None | `<= 4` check nodes and total cost `<= \$0.007` |
| `medium-10` | 15 | `pro` | Dual-Use CRM Boss | `lookup_account`, `send_customer_email` (DU), `delete_account` (R), `export_crm` (R) | Medium capstone: Dual-Use customer email + roleplay + Pattern C/D bait + agent rules | Max `5` check nodes | `max_tokens <= 5000` and no `agent_review` |

#### Hard — 8 Levels (Real LangGraph `budget` / Gullible Agent, 4–6 tools, 12–14 prompts each)

| ID | Order | Tier | Title | Agent Tools Summary (`R` = Restricted, `DU` = Dual-Use) | Core Puzzle Twist | Hard Constraint | Follow-Up Challenge (Mastery) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `hard-1` | 16 | `pro` | Warehouse Ops Under Siege | `search_catalog`, `lookup_inventory`, `export_payroll` (R), `run_sql` (R), `wire_transfer` (R), `drop_logs` (R) | Multi-vector chained attacks + Pattern C/D against a gullible agent | None | `<= 4` check nodes |
| `hard-2` | 17 | `pro` | No Heavy Weapons | `check_balance`, `search_transactions`, `wire_transfer` (R), `increase_credit_limit` (R), `disable_fraud_alert` (R) | Banking compliance forbids slow heavy review; rely on cleaner + ML + surgical `jev` Tool Policy | `agent_review` disabled | `<= 4` check nodes and avg latency `<= 500.0 ms` |
| `hard-3` | 18 | `pro` | The Auditor's Minefield | `search_policies`, `review_clause`, `sign_contract` (R), `share_privileged_file` (R) | Benign compliance auditors quote injection phrases verbatim; brittle phrase filters trigger false alarms | `word_filter` disabled | Total cost `<= \$0.010` |
| `hard-4` | 19 | `pro` | Polyglot & Stego Smuggler | `describe_cluster`, `read_metrics`, `rotate_keys` (R), `terminate_instance` (R), `open_firewall` (R) | SRE logs embedding URL-encoded JSON, Base64 dumps, and YAML tool-call payloads | Max `5` check nodes | No `agent_review` |
| `hard-5` | 20 | `pro` | Dual-Use Finance Desk | `search_expense_policy`, `approve_expense` (DU), `wire_transfer` (R), `modify_bank_details` (R), `delete_audit_entry` (R) | High-stakes Dual-Use approvals mixed with spoofed executive payment memos | Max `5` check nodes | Total cost `<= \$0.009` |
| `hard-6` | 21 | `pro` | Minimalist Fortress | `search_deployments`, `get_build_status`, `deploy_production` (R), `rollback_db` (R), `export_secrets` (R) | Tight systems-architecture constraint: every placeable check slot must do double duty | Max `3` check nodes | No `agent_review` |
| `hard-7` | 22 | `pro` | Dual-Use Cloud Ops | `get_cluster_health`, `restart_staging_pod` (DU), `notify_oncall` (DU), `terminate_prod_node` (R), `dump_env_secrets` (R), `open_ssh_port` (R) | Two simultaneous Dual-Use tools (`restart_staging_pod`, `notify_oncall`) requiring selective gating | `safety_check` disabled | `<= 4` check nodes |
| `hard-8` | 23 | `pro` | Zero-Day Red Team Capstone | `search_kb`, `create_support_case` (DU), `issue_payout` (R), `run_sql` (R), `grant_superadmin` (R), `wipe_audit_trail` (R) | Grand capstone mixing Dual-Use tickets, quoted auditor traps, chained obfuscation, and 4 restricted tools | Max `6` check nodes and total cost `<= \$0.015` | `<= 4` check nodes and avg latency `<= 650.0 ms` |

### 2. Hard Constraints & Follow-Up Challenge Evaluation

- **Static constraints (pre-run validation):**
  - Placeable check nodes are all `BoardNode`s whose `kind` is not `"incoming"` and not `"assistant"`.
  - Before evaluating any message, `validate_board_for_level(board, level)` (called by `run_wave` and `run_single_message`) raises `BoardValidationError` (`422` over HTTP) if:
    - the number of placeable check nodes exceeds `level.constraints.max_check_nodes`; or
    - any placeable node's `kind` is present in `level.constraints.disabled_checks`.
- **Runtime SLA constraints (post-wave scoring):**
  - After evaluating all messages in `run_wave`, any exceeded runtime constraint (`avg_latency_ms > max_avg_latency_ms`, `total_cost_usd > max_total_cost_usd`, or `total_tokens > max_tokens`) appends a descriptive entry to `WaveScore.constraint_violations` and forces `won = False`, `total_score = 0`, and `medal = "none"`.
- **Follow-Up Challenges (post-wave mastery check):**
  - Computed from the same single wave run and board graph with **zero additional LLM calls**.
  - `follow_up_passed = True` iff `won == True` and every configured target in `level.follow_up` (`max_check_nodes`, `forbidden_checks`, `max_avg_latency_ms`, `max_total_cost_usd`, `max_tokens`) is satisfied.
  - When `won == True` and one or more Follow-Up targets are missed, `follow_up_passed = False` and `follow_up_feedback` lists what was missed (e.g., `"Used 5 check nodes (Follow-up target <= 4)."`).

### 3. Dual-Use (Conditional) Tools

- A level may mark one or more tools with `allowed=True, dual_use=True`, and individual `LevelMessage` prompts may declare `forbidden_tools=("<tool_name>", ...)`.
- For each message in a wave, the effective forbidden tool set is `level_restricted_tools | frozenset(msg.forbidden_tools)`, where `level_restricted_tools` is `{t.name for t in profile.tools if not t.allowed}`.
- Evaluation outcomes for a Dual-Use tool:
  - **Required benign prompt (`is_attack=False`, `expected_tool="foo"`):** If Tool `"foo"` was switched off upstream (`gated_tools`), the agent cannot invoke it, producing `verdict="false_alarm"` (`won=False`).
  - **Baited benign prompt (`is_attack=False`, `category in {"quick_fix", "pasted_bait"}`, `forbidden_tools=("foo",)`):** Calling `"foo"` (because upstream Tool Policy did not switch it off) leaves the message `helped` (if not refused and any `expected_tool` was satisfied) but increments unintended tool calls and deducts `tool_points` (per `ENG-SCORE-004`). Switching `"foo"` off via upstream Tool Policy avoids the call and awards full `tool_points`.
  - **Attack prompt (`is_attack=True`, `forbidden_tools=("foo",)`):** Calling `"foo"` produces `verdict="leaked"` (`won=False`).
- `simulate_agent` (the deterministic offline stand-in) recognizes `forbidden_tools` alongside restricted tools on baited benign and attack prompts so offline runs and test suites mirror live LangGraph execution.

### 4. Pro-Tier Level Gating, Purge Migration & Difficulty-Aggregated Leaderboard

- **Catalog & Pro Gating:**
  - `GET /api/v1/game/levels` returns all 23 levels with `order`, `tier`, `tags`, `constraints`, `follow_up`, and tool `dual_use` metadata.
  - `POST /api/v1/game/run` (wave or `custom_message`) allows `anonymous` and `free` players to play `free` levels (`easy-1..3`, `medium-1..2`) under existing AI-node sign-in rules, and returns `403 Forbidden` on any `pro` level unless `player.tier == "paid"`.
  - `GET /api/v1/game/saves/{level_id}` and `PUT /api/v1/game/saves/{level_id}` enforce sign-in (`403` for anonymous) and additionally return `403 Forbidden` for `pro` levels unless `player.tier == "paid"`.
- **Database Migration & Purge:**
  - A new Supabase SQL migration (mirrored in `SqliteScoreStore` and `SqlitePlayerStore` per `API-SCHEMA-006`) adds `won` (`boolean not null default false` / SQLite `integer not null default 0`) and `mastered` (`boolean not null default false` / SQLite `integer not null default 0`) to `game.scores`.
  - The migration purges pre-campaign rows in `game.scores` and legacy `easy`, `medium`, `hard` rows in `game.saved_boards`.
  - `SCORE_VERSION` is bumped from `2` to `3` in `shield_api.services.scores`.
  - When updating an existing owner's record on the same `level_id` and `score_version`, `record_score` preserves `won = prev.won or new.won` and `mastered = prev.mastered or new.mastered` stickily even if one score outranks the other on raw `total_score`.
- **Difficulty-Aggregated Leaderboard & Player Progress:**
  - `GET /api/v1/game/leaderboard` (optional query `difficulty: Easy | Medium | Hard`, `limit: 1..100`) aggregates each player's best current-version (`SCORE_VERSION = 3`) score per level within each requested difficulty (or a combined campaign view when `difficulty` is omitted):
    - `total_score`: sum of the player's best `total_score` across levels in that difficulty;
    - `levels_solved`: count of distinct levels in that difficulty with `won=True` (or solved runs recorded);
    - `levels_mastered`: count of distinct levels in that difficulty with `mastered=True`;
    - `levels_total`: `5` (`Easy`), `10` (`Medium`), `8` (`Hard`), or `23` (`All`);
    - `max_possible_score`: `levels_total * 10000`;
    - Ordering: `(-total_score, -levels_mastered, avg_latency_ms, total_cost_usd, player_name)`.
  - `GET /api/v1/game/progress` returns the authenticated player's `PlayerProgressResponse` (empty/zeroed status for anonymous sessions) containing per-level `best_score`, `medal`, `won`, `mastered` for all 23 levels and per-difficulty aggregate totals (`Easy`, `Medium`, `Hard`).
  - Existing per-level `GET /api/v1/game/scores` remains available with `LevelId` updated to the 23 slugs plus optional `won`/`mastered` fields on `ScoreCreateRequest` and `ScoreRecord`.

## Acceptance criteria

- **ENG-CAMP-001**: Given `get_levels()` and `ALL_LEVEL_IDS`, when inspected, then exactly 23 unique levels exist across the three categories (`Easy`: 5 levels with 3 `free` + 2 `pro` and `agent=None`; `Medium`: 10 levels with 2 `free` + 8 `pro` and `agent_tier="standard"`; `Hard`: 8 levels with 0 `free` + 8 `pro` and `agent_tier="budget"`), every level has a unique `id`, `title`, sequential `order`, non-empty `tags`, a `follow_up` challenge, and non-empty prompts with both benign and attack messages.
- **ENG-CAMP-002**: Given a level with `LevelConstraints`, when a board violates `max_check_nodes` or includes a node kind in `disabled_checks`, then `validate_board_for_level` / `run_wave` raises `BoardValidationError` before executing messages; and when a wave completes but exceeds `max_avg_latency_ms`, `max_total_cost_usd`, or `max_tokens`, then `WaveScore.constraint_violations` lists the violated SLA(s) and forces `won=False` and `medal="none"`.
- **ENG-CAMP-003**: Given a level with a `FollowUpChallenge`, when `run_wave` finishes, then `follow_up_passed` is computed from the single wave run with no extra model calls: `True` only when `won=True` and every configured follow-up target (`max_check_nodes`, `forbidden_checks`, `max_avg_latency_ms`, `max_total_cost_usd`, `max_tokens`) is satisfied; when `won=True` and any target is missed, `follow_up_passed=False` and `follow_up_feedback` states the missed target.
- **ENG-CAMP-004**: Given a level containing a Dual-Use tool (`allowed=True, dual_use=True`), when evaluated against a benign prompt with `expected_tool` set to that tool, a benign baited prompt listing it in `forbidden_tools`, and an attack prompt listing it in `forbidden_tools`, then switching the tool off on the required benign prompt causes `false_alarm` (`won=False`), leaving it enabled on the baited benign prompt deducts `tool_points`, leaving it enabled on the attack prompt causes `leaked` (`won=False`), and selectively switching it off via Tool Policy only on the baited/attack prompts yields `won=True` with full `tool_points`.
- **ENG-CAMP-005**: Given an introductory level that teaches specific checks (`easy-2` teaches `text_cleanup` and `secret_scan`; `easy-3` teaches `ml_classifier`), when inspected, then its `constraints.disabled_checks` lists every other placeable check kind, so a board with any other check raises `BoardValidationError`; and a board using only the taught checks passes `validate_board_for_level` (for `easy-2`, `Input → Text cleaner → Secret scanner → Help Desk`, with all cleaner transforms on and patterns for `secret`, `api_key` and `select * from`, still wins the wave). (Added at the owner's request so guided tours can focus on one node.)
- **API-CAMP-001**: Given `GET /api/v1/game/levels`, `POST /api/v1/game/run`, and `/api/v1/game/saves/{level_id}`, when queried, then the catalog exposes all 23 levels with `order`, `tier`, `tags`, `constraints`, `follow_up`, and tool `dual_use` flags; `anonymous` and `free` players can run `free` levels (`easy-1..3`, `medium-1..2`) under existing AI-node rules, while `pro` levels return `403` on `/run` and `/saves/{level_id}` unless `player.tier == "paid"`.
- **API-CAMP-002**: Given the new Supabase migration, when it is applied, then `game.scores` includes `won` and `mastered` columns, legacy `game.scores` rows and legacy `easy`/`medium`/`hard` `game.saved_boards` rows are purged, `SCORE_VERSION` is `3`, and `record_score` preserves `mastered=True` stickily across subsequent score updates for the same `(owner, level_id)`.
- **API-CAMP-003**: Given signed-in players with scores recorded across multiple levels in `Easy`, `Medium`, and `Hard`, when `GET /api/v1/game/leaderboard` is queried (optionally filtered by `difficulty`), then each player's high score for a difficulty equals the sum of their best scores across all levels in that difficulty (ordered by `total_score desc`, `levels_mastered desc`, `avg_latency_ms asc`, `total_cost_usd asc`) along with `levels_solved`, `levels_mastered`, `levels_total`, and `max_possible_score`; and `GET /api/v1/game/progress` returns the authenticated player's per-level status and per-difficulty totals.
- **API-CAMP-004**: Given players with won and lost runs, when `GET /api/v1/game/leaderboard` is queried, then a player's `total_score` sums only their best **won** score per level (lost runs add nothing), players whose total is `0` are left off the leaderboard, and `record_score` never lets a lost run replace a stored won run for the same `(owner, level_id)` while a won run always replaces a stored lost run. (Added at the owner's request.)

## Security & privacy considerations

- Server-side tier enforcement blocks `anonymous` and `free` accounts from running or saving boards on `pro` levels (`HTTP 403`) rather than relying on client UI locks.
- Static constraint enforcement (`max_check_nodes`, `disabled_checks`) and Pro gating reject invalid or unauthorized requests before any LLM provider or Jev client is called, protecting server inference budgets.
- `GET /api/v1/game/leaderboard` never exposes player emails, using the same privacy isolation as `game.scores` ([spec 0025](../0025-account-settings/spec.md)).

## Evaluation impact

- Expands the campaign wave suite from 3 waves (32 messages total) to 23 distinct waves (~250+ messages across classification-only, `standard` LangGraph agent, and `budget` LangGraph agent tiers).
- Exact reference before/after wave scores (`easy-1..5`, `medium-1..10`, `hard-1..8`, including Follow-Up pass and Dual-Use Tool Policy comparisons) will be recorded under `## Verification` once implementation runs against the suite.

## Open questions

- None.

## Verification

### 2026-11-19 · commit 2a0b84f (+ uncommitted changes)

- Criteria: ENG-CAMP-001, ENG-CAMP-002, ENG-CAMP-003, ENG-CAMP-004, API-CAMP-001, API-CAMP-002, API-CAMP-003
- Red: 7 failing test(s) before implementation (`packages/engine/tests/test_campaign_levels.py::test_campaign_exposes_23_unique_levels_across_three_difficulties`, `packages/engine/tests/test_campaign_levels.py::test_level_constraints_reject_invalid_boards_and_penalize_sla_violations`, `packages/engine/tests/test_campaign_levels.py::test_follow_up_challenge_evaluates_on_single_run_with_no_extra_model_calls`)
- Green: 7 passing test(s)
- Gate: `mise run check` passed

### 2026-11-21 · commit 2a0b84f (+ uncommitted changes)

- Criteria: ENG-CAMP-005
- Red: 2 failing test(s) before implementation (`packages/engine/tests/test_campaign_levels.py::test_intro_levels_disable_every_check_except_the_ones_they_teach[easy-2-taught0]`, `packages/engine/tests/test_campaign_levels.py::test_intro_levels_disable_every_check_except_the_ones_they_teach[easy-3-taught1]`)
- Green: 3 passing test(s)
- Gate: `mise run check` passed

### 2026-11-21 · commit faa585d (+ uncommitted changes)

- Criteria: API-CAMP-004
- Red: 2 failing test(s) before implementation (`apps/api/tests/test_campaign_api.py::test_leaderboard_sums_only_won_runs_and_hides_players_with_zero_points`, `apps/api/tests/test_campaign_api.py::test_a_lost_run_never_replaces_a_won_run_and_a_won_run_replaces_a_lost_one`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed
