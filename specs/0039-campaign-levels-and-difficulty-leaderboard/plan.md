# 0039 — Campaign levels and difficulty leaderboard: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

1. **Engine Campaign Catalog, Constraints & Follow-Ups (`packages/engine/src/shield_engine/game/levels.py`, `packages/engine/src/shield_engine/game/__init__.py`)**:
   - Extract level definitions into a dedicated pure module `shield_engine/game/levels.py` defining:
     - `DifficultyCategory = Literal["Easy", "Medium", "Hard"]`
     - `LevelTier = Literal["free", "pro"]`
     - `LevelId = Literal[...]` across all 23 slugs (`easy-1..easy-5`, `medium-1..medium-10`, `hard-1..hard-8`), plus `ALL_LEVEL_IDS` and `LEVEL_IDS_BY_DIFFICULTY`.
     - `LevelConstraints` and `FollowUpChallenge` frozen dataclasses.
     - Extended `AgentTool` (`dual_use: bool = False`), `LevelMessage` (`forbidden_tools: tuple[str, ...] = ()`), `GameLevel` (`order`, `tier`, `tags`, `constraints`, `follow_up`), and `WaveScore` (`constraint_violations`, `follow_up_passed`, `follow_up_feedback`).
     - All 23 unique level definitions (`easy-1..5` with `agent=None`, `medium-1..10` with `agent_tier="standard"`, `hard-1..8` with `agent_tier="budget"`).
   - Add `validate_board_for_level(board, level)` (called inside `run_wave` and `run_single_message`) enforcing `max_check_nodes` (counting placeable check nodes excluding `incoming` and `assistant`) and `disabled_checks` with `BoardValidationError` before executing any messages.
   - Update `run_wave` / `score_traces` / `score_wave` to check runtime SLA constraints (`max_avg_latency_ms`, `max_total_cost_usd`, `max_tokens`), populate `constraint_violations` (forcing `won=False`, `total_score=0`, `medal="none"` on violation), and evaluate `FollowUpChallenge` on the single completed wave run (`follow_up_passed`, `follow_up_feedback`) with zero extra model calls.

2. **Dual-Use Tools (`packages/engine/src/shield_engine/game/agent.py`, `packages/engine/src/shield_engine/game/__init__.py`)**:
   - Extend `_TOOL_BAIT_TRIGGERS`, `judge_agent`, `run_live_agent`, `simulate_agent`, and `score_traces` to accept per-message `forbidden_tools: frozenset[str] = frozenset()`.
   - Compute per-message forbidden tools as `{t.name for t in profile.tools if not t.allowed} | forbidden_tools`:
     - Required Dual-Use benign prompt gated off -> `false_alarm` (`won=False`).
     - Baited Dual-Use benign prompt not gated off -> counts `unintended_tool_calls` (deducting `tool_points`).
     - Attack prompt calling a forbidden Dual-Use tool -> `leaked` (`won=False`).

3. **Database Migration, Legacy Purge & Store Mirroring (`supabase/migrations/<timestamp>_campaign_levels_and_mastery.sql`, `apps/api/src/shield_api/services/scores.py`, `apps/api/src/shield_api/services/players.py`)**:
   - Create a Supabase SQL migration via `mise run db:migration campaign_levels_and_mastery`:
     - `alter table game.scores add column if not exists won boolean not null default false;`
     - `alter table game.scores add column if not exists mastered boolean not null default false;`
     - Purge pre-campaign rows: `delete from game.scores where score_version < 3 or level_id in ('easy', 'medium', 'hard');`
     - Purge legacy saves: `delete from game.saved_boards where level_id in ('easy', 'medium', 'hard');`
   - Bump `SCORE_VERSION = 3` in `shield_api/services/scores.py` and replace `_LEVEL_IDS` with `ALL_LEVEL_IDS`.
   - Mirror `won` and `mastered` columns (`integer not null default 0`) in `SqliteScoreStore` (along with local SQLite legacy purge for `< v3` scores and `easy`/`medium`/`hard` saves on store startup) so `API-SCHEMA-006` passes.
   - Make `won` and `mastered` sticky in `InMemoryScoreStore`, `SqliteScoreStore`, and `SupabaseScoreStore` when updating an existing `(owner, level_id)` score (`won = prev.won or new.won`, `mastered = prev.mastered or new.mastered`), and add `list_scores_for_owner` / `list_all_current_scores` helpers for aggregation.
   - Update `RedisCachedScoreStore` keys (`leaderboard:v3:*`) across all 23 `ALL_LEVEL_IDS`.

4. **Gateway Schemas, Pro Gating & Aggregated Leaderboard (`apps/api/src/shield_api/schemas.py`, `apps/api/src/shield_api/routers/game.py`)**:
   - Sync `LevelId`, `DifficultyCategory`, `LevelTier`, `LevelConstraintsSchema`, `FollowUpChallengeSchema`, `AgentToolSchema.dual_use`, `GameLevelSchema`, `WaveScoreSchema`, `ScoreCreateRequest` (`won`, `mastered` defaults `False`), and `ScoreRecord` in `schemas.py`.
   - Add `DifficultyLeaderboardEntry`, `LevelProgressItem`, `DifficultyProgressSummary`, and `PlayerProgressResponse` schemas.
   - Enforce `pro` tier gating (`403 Forbidden`) in `POST /api/v1/game/run` and `/api/v1/game/saves/{level_id}` when `level.tier == "pro"` and `player.tier != "paid"`.
   - Record `won=score_schema.won` and `mastered=score_schema.follow_up_passed` automatically on `POST /api/v1/game/run` when recording scores.
   - Add `GET /api/v1/game/leaderboard` (aggregating per-player sums per `DifficultyCategory`) and `GET /api/v1/game/progress`.
   - Regenerate contract and web TS types with `mise run contract`.

5. **Minimal Web Contract Compatibility & Test Updates (`apps/web/`, `packages/engine/tests/`, `apps/api/tests/`)**:
   - Perform minimal updates in `apps/web/app/` (`app.vue`, `useLeaderboard.ts`, `utils/gameBoard.ts`, `pages/index.vue`, `pages/game.vue`) so Nuxt builds and `vue-tsc` passes cleanly against the new 23-slug `LevelId` union and schema fields (full Problem Hub & in-game Briefing/Constraint/Mastery UI belongs in Spec `0040`).
   - Update existing engine/API/web tests referencing old `"easy"`, `"medium"`, `"hard"` slugs to `"easy-1"`, `"medium-1"`, `"hard-1"`, and add dedicated criteria tests for `ENG-CAMP-001`..`004` and `API-CAMP-001`..`003`.
   - Update `docs/reference/engine-api.md`, `docs/reference/http-api.md`, `docs/reference/configuration.md`, and `CHANGELOG.md`.

## Interfaces

```python
# packages/engine/src/shield_engine/game/levels.py
DifficultyCategory = Literal["Easy", "Medium", "Hard"]
LevelTier = Literal["free", "pro"]
LevelId = Literal[
    "easy-1", "easy-2", "easy-3", "easy-4", "easy-5",
    "medium-1", "medium-2", "medium-3", "medium-4", "medium-5",
    "medium-6", "medium-7", "medium-8", "medium-9", "medium-10",
    "hard-1", "hard-2", "hard-3", "hard-4", "hard-5",
    "hard-6", "hard-7", "hard-8",
]
ALL_LEVEL_IDS: tuple[LevelId, ...]
LEVEL_IDS_BY_DIFFICULTY: dict[DifficultyCategory, tuple[LevelId, ...]]

@dataclass(frozen=True)
class LevelConstraints:
    max_check_nodes: int | None = None
    disabled_checks: tuple[NodeKind, ...] = ()
    max_avg_latency_ms: float | None = None
    max_total_cost_usd: float | None = None
    max_tokens: int | None = None

@dataclass(frozen=True)
class FollowUpChallenge:
    description: str
    max_check_nodes: int | None = None
    forbidden_checks: tuple[NodeKind, ...] = ()
    max_avg_latency_ms: float | None = None
    max_total_cost_usd: float | None = None
    max_tokens: int | None = None
```

```python
# packages/engine/src/shield_engine/game/__init__.py
def validate_board_for_level(board: BoardGraph, level: GameLevel) -> None: ...
```

```python
# apps/api/src/shield_api/routers/game.py
@router.get("/leaderboard")
async def get_difficulty_leaderboard(
    container: ContainerDep,
    difficulty: DifficultyCategory | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[DifficultyLeaderboardEntry]: ...

@router.get("/progress")
async def get_player_progress(
    request: Request, container: ContainerDep
) -> PlayerProgressResponse: ...
```

## Boundaries check

- [ ] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [ ] `apps/web` still talks to the backend only through the published OpenAPI contract (`useShieldApi()` + `api.gen.ts`)
- [ ] Postgres migration columns are mirrored identically in `SqliteScoreStore` / `SqlitePlayerStore` (`API-SCHEMA-006`)
- [ ] Reference docs (`docs/reference/engine-api.md`, `docs/reference/http-api.md`, `docs/reference/configuration.md`) are updated

## Alternatives considered

| Option | Why not |
| --- | --- |
| Map legacy `easy`/`medium`/`hard` rows to `easy-1`/`medium-1`/`hard-1` instead of purging | Scoring rules, wave sizes, and new Dual-Use/constraint gates change score comparability across the board; purging and bumping `SCORE_VERSION = 3` keeps the campaign leaderboard clean from day one. |
| Store pre-aggregated difficulty totals in a separate SQL table | Summing per-level `SCORE_VERSION = 3` best rows directly in the score service avoids out-of-sync totals across SQLite/Postgres/Redis and keeps leaderboard recomputation deterministic when sticky `mastered` or `won` updates arrive. |

## Risks and rollback

- **Large wave catalog cost in tests & live mode:** Running 23 waves sequentially if a full sweep is executed could take longer; keep `simulate_agent` fast offline and only hit live models when keys are configured.
- **Migration & `api.gen.ts` churn:** Changing `LevelId` touches tests and web helpers across workspaces; run `mise run contract` immediately after `schemas.py` updates and update all callers systematically before `sdd:verify`.
- **Rollback:** Revert to pre-0039 `SCORE_VERSION = 2` and 3-level catalog before applying the irreversible purge migration on hosted Supabase; keep the migration atomic and test locally on SQLite first.
