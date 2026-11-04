# 0017 Plan: Game gateway API and scoreboard storage

## Architecture

- Extend `apps/api/src/shield_api/schemas.py` with Pydantic models for `BoardNodeSchema`, `BoardEdgeSchema`, `BoardGraphSchema`, `GameLevelSchema`, `GameRunRequest`, `GameRunResponse`, `ScoreCreateRequest`, `ScoreRecord`.
- Add `scores` table to `SqliteAuditLog` (and migration `supabase/migrations/`) with `record_score`, `list_scores`, and `clear_scores` methods.
- Add `/api/v1/game/*` routes in `apps/api/src/shield_api/routes/game.py` and wire them in `main.py` and `container.py`.
- Run `mise run contract` to update `contracts/shield-api.openapi.json` and `apps/web/app/types/api.gen.ts`.
