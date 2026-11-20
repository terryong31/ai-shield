# Plan — 0033 Saved board return check and instant loading state

1. **`apps/web/app/composables/useSavedBoardCache.ts`** (or state helper in `gameBoard.ts` + `usePlayerAuth.ts`):
   - Hold a `useState<Record<string, SavedBoardRequest | null>>('shield_saved_boards_cache', () => ({}))` map keyed by `${playerKey}:${levelKey}` so cached boards never bleed across accounts and clear on logout/reset.
2. **`apps/web/app/pages/game.vue`**:
   - Add `handleReturnClick()`:
     - For signed-in players with `!hasUnsavedChanges`: call `goBack('/')` directly without opening `isQuitModalOpen`.
     - For anonymous players whose board matches the starter signature (`currentSignature === starterSignature`): call `goBack('/')` directly.
     - Otherwise open `isQuitModalOpen = true`.
   - Add `isLoadingBoard = ref(true)` (skipped when a cached board is immediately restored):
     - Show a clean centered loading overlay inside `<main>` (`v-if="isLoadingBoard"`) while the initial `loadSavedBoard` fetch runs.
     - Parallelize `refreshSession()`, `getLevels()`, and `loadSavedBoard()` with `Promise.all(...)` in `onMounted`.
   - Update `handleSaveBoard()` to write the saved board into the client cache immediately after `putSave` succeeds.
