# Plan — 0032 System .env-only API keys

1. **API (`apps/api`)**:
   - Remove `jev_api_key`, `ai_api_key`, `ai_provider` from `GameRunRequest` in `schemas.py`.
   - Update `routers/game.py` to use `container.jev_client` and `container.game_agent` directly (no `raw_jev_key` / `raw_ai_key`).
   - Run `mise run contract` to update `contracts/shield-api.openapi.json` and `apps/web/app/types/api.gen.ts`.
2. **Web (`apps/web`)**:
   - Update `nodeKeyRequirement` in `gameBoard.ts` to instruct adding the key in the system `.env`.
   - Remove `isApiKeyModalOpen`, `apiKeyModalKind`, `jevApiKey`, `aiApiKey`, `aiKeyProvider`, and all API key input UIs from `game.vue`.
   - In `placeCheck` in `game.vue`, show a toast informing the user to add the API key in the system `.env` when `nodeKeyRequirement` returns a message, and never place the node.
