# 0048 — Display name: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

Add `set_player_name` to the player stores, `rename_scores_player` to the score stores and `on_owner_display_name` to `LeaderboardService` (Lua update of the `:name` field). Add the route in `routers/account.py` and a modal row in `settings.vue`. Run `mise run contract`.

## Boundaries check

- [ ] The engine does not change
- [ ] The web client uses only the contract
- [ ] New configuration is in `docs/reference/configuration.md`

## Risks and rollback

Revert the release; new columns and tables are additive.
