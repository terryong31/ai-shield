# 0033 — Saved board return check and instant loading state

- **Status:** Implemented
- **Area:** WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-17
- **Related:** [0023-game-saved-boards](../0023-game-saved-boards/spec.md)

## Problem

1. **Return always warns about losing progress even right after clicking Save.** Clicking **Return** in `/game` unconditionally opens the `"Quit Game — Are you sure you want to quit? Your progress will not be saved"` modal, even when `hasUnsavedChanges` is `false` (no edits since saving, or board unchanged).
2. **Saved workflows take 2–3 seconds and pop onto an already-visible empty canvas.** `onMounted` in `/game` runs `refreshSession()`, `getLevels()`, and `loadSavedBoard()` sequentially instead of in parallel, and renders the empty starter canvas before the saved board arrives, causing a sudden visual jump after 2–3 seconds.

## Goals

- Skip the quit confirmation modal and return straight to the menu when there are no unsaved changes (`!hasUnsavedChanges` and board matches initial/saved state). Only prompt when the player actually has unsaved edits.
- Cache saved boards in client state (`useState`) on save/load and parallelize initial mount fetches (`refreshSession`, `getLevels`, `loadSavedBoard`) so re-opening a saved workflow renders immediately without a 2–3 second delay.
- Display a clean UI loading state over the canvas (`isLoadingBoard`) whenever a saved board is still being fetched from the backend so the canvas never flashes an empty starter board and suddenly pops.

## Non-goals

- Changing backend `/api/v1/game/saves/{level_id}` endpoints or database storage.

## Behaviour

- **Return button (`handleReturnClick`)**:
  - When signed in and `!hasUnsavedChanges`: navigates directly back (`goBack('/')`) without opening `isQuitModalOpen`.
  - When anonymous and the board differs from the starter board, or when signed in and `hasUnsavedChanges` is `true`: opens `isQuitModalOpen` to warn about unsaved progress.
- **Fast loading + UI loading overlay**:
  - Client `useSavedBoardCache` (`useState<Record<string, SavedBoardResponse | null>>`) stores saved boards per level (`easy`, `medium`, `hard`, `custom`) and is updated immediately on `putSave` and `getSave` (and cleared on logout/reset).
  - `onMounted` runs `refreshSession()`, `getLevels()`, and `loadSavedBoard()` concurrently (`Promise.all`).
  - If a cached save exists for the current level, it is applied immediately on mount (0 ms) while revalidating in the background.
  - Otherwise, `isLoadingBoard` is `true` until `loadSavedBoard()` resolves, displaying a loading indicator over the canvas so the empty starter board does not flash before the saved workflow appears.

## Acceptance criteria

- **WEB-SAVE-003**: Given `/game` when there are no unsaved changes (e.g. immediately after `handleSaveBoard` completes), when the player clicks **Return**, then `isQuitModalOpen` stays `false` and the client navigates back without showing the unsaved-progress warning; when there are unsaved changes, clicking **Return** opens `isQuitModalOpen`.
- **WEB-SAVE-004**: Given `/game` on mount or level switch, when loading a saved board, then `refreshSession`, `getLevels`, and `loadSavedBoard` run concurrently, saved boards are cached in client state for immediate restoration, and `isLoadingBoard` renders a UI loading overlay over the canvas while a remote save is being fetched.

## Security & privacy considerations

- Client cache stores only board topology and node positions (never API keys or secrets) and is cleared on player logout or progress reset.

## Evaluation impact

- None.

## Open questions

- None.

## Verification

### 2026-11-17 · commit 2a0b84f (+ uncommitted changes)

- Criteria: WEB-SAVE-004
- Red: 1 failing test(s) before implementation (`saved boards (spec 0023) [WEB-SAVE-004] parallelizes mount fetches, caches saved boards, and shows a loading overlay over the canvas`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed
