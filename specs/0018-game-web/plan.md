# 0018 Plan: Web Defender game, landing page, and admin console

## Architecture

- **State & API (`useShieldApi.ts` & `useGameBoard.ts`):**
  - Add `getLevels()`, `runGame()`, `getScores()`, `submitScore()`, and `clearScores()` to `useShieldApi.ts`.
  - Create `app/utils/gameBoard.ts` (pure functions for starter boards, adding/removing nodes, connecting edges, and applying hop traces) and `app/composables/useGameBoard.ts`.
- **Pages:**
  - `app/pages/index.vue`: High-contrast monochrome landing page with level cards and scoreboard.
  - `app/pages/game.vue`: Interactive Vue Flow board, check palette, wave runner, custom message tester, BYOD drawer, and score submission modal.
  - `app/pages/console/index.vue`, `logs.vue`, `settings.vue`: Admin console served at `/_console`, `/_console/logs`, `/_console/settings`, guarded by admin clearance state.
  - Redirect `/dashboard*` to `/_console*`.
- **Design Hygiene:**
  - Replace all legacy palette classes (`text-emerald-400`, `bg-zinc-900`, etc.) and raw HTML controls in `components/workflow/*` and `components/chat/*` with Nuxt UI semantic tokens and components.
