# 0023 — Saved boards

- **Status:** Implemented
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-08
- **Related:** [spec 0021](../0021-game-level-tiers/spec.md) (level tiers), [spec 0022](../0022-game-custom-sandbox/spec.md) (custom sandbox), [plan.md](plan.md), [tasks.md](tasks.md)

## Problem

A board lives only in the page. Reloading `/game` or switching device resets
it to the starter board (`createStarterBoard` in `app/utils/gameBoard.ts`).
The only board the gateway stores is the snapshot attached to a leaderboard
score (`board_json` in the scores table). For the custom sandbox
(spec 0022) this is worse: the agent profile and dataset are lost on reload
too.

## Goals

- Signed-in players can **save** their board for each level and get it back
  when they open that level again, on any device.
- In custom mode, the save also holds the agent profile, the dataset and the
  chosen provider and model, **never** the API key.
- Saving is an explicit action (a `Save` button), not autosave.

## Non-goals

- Several named saves per level. One slot per player per level.
- Saving for anonymous players.
- Saving or storing API keys in any form.
- Version history of a save.

## Behaviour

### Storage

- Saves live in `game.saved_boards (email, level_id, save_json, updated_at)`
  with primary key `(email, level_id)`, created by spec 0024 in both the
  Supabase migration and the SQLite `game` domain file. `PlayerStore` gains
  `load_board` and `save_board`, implemented by `InMemoryPlayerStore`,
  `SqlitePlayerStore` and `SupabasePlayerStore`.
- A save replaces the previous save for that level.

### HTTP

| Route | Who | Result |
| --- | --- | --- |
| `GET /game/saves/{level_id}` | signed-in | `200` with the save, or `404` when there is none |
| `PUT /game/saves/{level_id}` | signed-in | `200` with the stored save |
| either, anonymous or no session | | `403 Sign in to save your board.` |
| either, `level_id = "custom"` and not paid | | `403` |

`level_id` is `easy`, `medium`, `hard` or `custom`.

The save body:

```json
{
  "board": { "nodes": [...], "edges": [...] },
  "positions": { "incoming": { "x": 0, "y": 120 }, "word_filter": { "x": 240, "y": 120 } },
  "custom": {
    "agent": { "objective": "...", "tools": [...], "token_budget": 0 },
    "dataset": [{ "text": "...", "label": "normal", "expected_tool": null }],
    "provider": "openai",
    "model": "gpt-4.1-mini"
  }
}
```

- `custom` is allowed only for `level_id = "custom"`, and is `null` otherwise.
- The custom object has **no** key field. Unknown fields are rejected
  (`422`), so a client that sends `api_key` in a save gets an error rather
  than having it stored.
- Limits: up to 60 nodes and 200 edges, and a body of up to 256 KB
  (`413` above that). The board is **not** checked with `validate_board`,
  because work in progress may be unwired; it is checked when it runs.
- The response adds `level_id` and `updated_at`.

### Web

- The run bar on `/game` has a `Save` button next to `Restart`.
  - Signed in: saves the board, node positions and (custom) setup, then
    shows `Saved` as a toast.
  - Anonymous: opens the sign-in prompt (`Sign in to save your board.`).
  - When the board has changed since the last save or load, the button shows
    a dot so the player knows there is unsaved work.
- Opening a level loads the save if there is one; otherwise the starter
  board. A save that no longer loads (for example a node kind that was
  removed) falls back to the starter board and shows a toast.
- `Restart` resets the board on screen; it does not delete the save.
- In custom mode the API key field stays empty after loading a save.

## Acceptance criteria

- **API-SAVE-001**: Given a signed-in player, when they `PUT` a board with positions to `/game/saves/medium` and then `GET` it, then the same board and positions come back with `level_id` and `updated_at`, a second `PUT` replaces the first, and a `GET` for a level with no save returns `404`.
- **API-SAVE-002**: Given an anonymous session or no session, when it calls `GET` or `PUT` on `/game/saves/{level_id}`, then the response is `403` and nothing is stored.
- **API-SAVE-003**: Given a free player, when they `PUT` or `GET` `/game/saves/custom`, then the response is `403`; given a paid player, the custom agent, dataset, provider and model are stored and returned.
- **API-SAVE-004**: Given a save body whose `custom` object includes `api_key` or any unknown field, or a `custom` object on a non-custom level, when it is posted, then the response is `422` and nothing is stored.
- **API-SAVE-005**: Given a save with more than 60 nodes or 200 edges, the response is `422`; given a body over 256 KB, the response is `413`; and an unwired board within the limits is accepted.
- **API-SAVE-006**: Given the SQLite store, when the gateway restarts, then saves are still there, and the in-memory, SQLite and Supabase stores behave the same for save and load, with Supabase reading and writing `game.saved_boards`.
- **WEB-SAVE-001**: Given `/game`, when the run bar renders, then it has a `Save` button that saves through `useShieldApi()` for signed-in players, opens the sign-in prompt for anonymous players, and shows a dot while the board has unsaved changes.
- **WEB-SAVE-002**: Given a level with a save, when `/game` opens it, then the saved board and positions are restored; a save that fails to load falls back to the starter board with a toast; and in custom mode the key field stays empty.

## Security & privacy considerations

- **Keys are never stored.** The save schema has no key field and rejects
  unknown fields, so a key cannot reach the database by mistake.
- **Players only see their own saves.** Saves are keyed by the account email
  from the session, never by a value in the request.
- **Size limits** stop the endpoint being used as free storage.
- **Saved text is player data.** Custom objectives, tools and dataset rows are
  stored as given and only ever sent back to the same player, or, when they
  run, to their own model wrapped as untrusted data (spec 0022).

## Evaluation impact

None. No detection change.

## Open questions

None.

## Verification

_Filled in by `mise run sdd:done`._

### 2026-11-08 · commit ce5746e (+ uncommitted changes)

- Criteria: API-SAVE-001, API-SAVE-002, API-SAVE-003, API-SAVE-004, API-SAVE-005, API-SAVE-006, WEB-SAVE-001, WEB-SAVE-002
- Red: 8 failing test(s) before implementation (`apps/api/tests/test_game_saves_api.py::test_save_and_load_round_trip_and_replace`, `apps/api/tests/test_game_saves_api.py::test_anonymous_players_cannot_save_or_load`, `apps/api/tests/test_game_saves_api.py::test_custom_saves_are_for_paid_players`)
- Green: 8 passing test(s)
- Gate: `mise run check` passed
