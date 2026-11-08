# 0023 — Saved boards: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

- `PlayerStore` gains `load_board(email, level_id)` and
  `save_board(email, level_id, save_json)`; the in-memory, SQLite and Supabase
  stores implement them against `game.saved_boards` (spec 0024).
- New router module `routers/saves.py` (or routes in `routers/game.py`)
  resolves the player from the session cookie, enforces tier rules and size
  limits, and stores the save as JSON.
- Schemas: `SavedBoardRequest`, `SavedBoardResponse`, `CustomSetupSchema`
  (`extra="forbid"`), `NodePositionSchema`.
- Web: `getSave` and `putSave` in `useShieldApi()`; `game.vue` loads on open
  and tracks a `savedSignature` (JSON of the last saved board) to show the
  unsaved dot.

## Boundaries check

- [ ] `packages/engine` is unchanged
- [ ] `apps/web` still talks to the backend only through the published OpenAPI contract
- [ ] No key field anywhere in the save schema

## Alternatives considered

| Option | Why not |
| --- | --- |
| Autosave on every change | A write per node drag; explicit save was chosen |
| Browser `localStorage` | Not shared across devices |

## Risks and rollback

- Saves of node kinds removed later fail to load; the web falls back to the
  starter board.
- Rollback: hide the `Save` button; the table can stay.
