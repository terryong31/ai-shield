# 0040 — Minimal monochrome Level Select and in-game briefing UI: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

1. **Pure Campaign UI Helpers (`apps/web/app/utils/campaignSelect.ts`)**:
   - Export framework-free TypeScript helpers cleanly unit-tested in Vitest:
     - `canAccessLevel(level, session)` returning `'available' | 'pro_locked'`.
     - `buildCategorySummaries(levels, session)` returning `Easy` (5), `Medium` (10), and `Hard` (8) poster card metadata (`levelsCount`, `locked`, descriptions, emblem icons — omitting progress bars and scores).
     - `buildLevelTiles(levels, progressByLevel, difficulty, session)` returning ordered numbered tiles (`01`..`10`) with 3-star `UInputRating` count (`(won ? 1 : 0) + (medal === 'gold' ? 1 : 0) + (mastered ? 1 : 0)`), `locked` flag (`tier === 'pro'` for non-paid players), `isBoss` (`easy-5`, `medium-10`, `hard-8`), and high-contrast visual style metadata.
     - `difficultyBadgeColor(difficulty)` and `toolRoleBadge(tool)` mapping badges via helper functions without putting literal `color="error"` attributes on non-`UButton` elements (`WEB-UI-005`).
     - `nextCampaignLevel(levels, currentLevelId)` returning the next sequential level by `order`.
     - `countPlacedCheckNodes(nodes)` excluding `incoming` and `assistant`.

2. **API Client & Leaderboard Composable (`apps/web/app/composables/useShieldApi.ts`, `apps/web/app/composables/useLeaderboard.ts`, `apps/web/app/types/api.ts`)**:
   - Export generated aliases for `DifficultyCategory`, `DifficultyLeaderboardEntry`, `PlayerProgressResponse`, `LevelConstraintsSchema`, and `FollowUpChallengeSchema` in `app/types/api.ts`.
   - Add `getLeaderboard(difficulty?, limit)` and `getProgress()` to `useShieldApi()`.
   - Update `useLeaderboard.ts` so `selectedTab` tracks `DifficultyCategory` (`'Easy' | 'Medium' | 'Hard'`), fetches `getLeaderboard()`, and refreshes cleanly on SSE events from `/api/v1/game/scores/stream`.

3. **2-Step Minimal Level Select & Leaderboard (`apps/web/app/components/campaign/`, `apps/web/app/pages/index.vue`)**:
   - Keep `index.vue` ultra-clean using Nuxt UI semantic tokens, default `font-sans` typography (zero `font-mono` or `Roboto`), and high-contrast WCAG AA/AAA rules:
     - **View 1 (Main Menu + Leaderboard):** `Easy` / `Medium` / `Hard` tabs over `DifficultyLeaderboardEntry[]` (`Rank`, `Player`, `Total Score`, `Cleared`, `Mastered`, `Avg Speed`, `Cost`) with `UEmpty` when empty.
     - **View 2, Step 1 (`?view=levels`):** Clean solid dark `bg-default` surface (`neutral-900`, `#171717`) matching the Main Menu page (no grid lines, never pitch-black `#09090b`) with 3 vertical monochrome `UPageCard` spotlight poster cards (`Easy` 5, `Medium` 10, `Hard` 8), centered geometric emblems, no progress bar/cleared count/score clutter, and blurred + padlock overlay on locked `Hard` (clicking opens `UpgradeProModal` linking to `/plans`), plus understated Custom Sandbox strip preserving `customModeAccess(session)`.
     - **View 2, Step 2 (`?view=levels&difficulty=easy|medium|hard`):** Minimal top header (`Back`, `Select Level` + difficulty `UBadge`), centered `5x1` / `5x2` / `4x2` numbered tile grid (`LevelTileGrid.vue`) with `<UInputRating :length="3" readonly>` per tile and blurred + padlock overlay on locked tiles (no top-right total score or bottom difficulty switcher); clicking unlocked tiles opens `LevelBriefingModal.vue` and clicking Pro-locked tiles opens the Upgrade to Pro `UModal` (`#header/#body/#footer` slots, using Nuxt UI's native icon-only `i-lucide-x` close button in the header with no `"Close"` text word).

4. **In-Game Campaign UX (`apps/web/app/pages/game.vue`, `apps/web/app/utils/gameBoard.ts`)**:
   - Sync `disabled_checks` and `max_check_nodes` from the active `GameLevelSchema` into palette drag/drop gating (`"Disabled in this level"` `UTooltip`) and a live check-node counter badge in the board header.
   - Render a `UEmpty` / `UCard` Pro lock gate when a non-paid user navigates directly to a `pro` level URL.
   - Add a **Mission Briefing** `UModal` (`#header/#body/#footer`) showing tools (`Safe` / `Restricted` / `Dual-Use`), Hard Constraints, and Mastery Star objective.
   - Update the Run Results `UModal` to display `constraint_violations` (`UAlert`), `Mastered` celebration (`i-lucide-star`) / `follow_up_feedback`, and `Next Level` + `Back to Levels` (`/?view=levels&difficulty=...`) actions.

5. **Tests & Hygiene Verification (`apps/web/test/campaignSelect.test.ts`, `apps/web/test/game.test.ts`)**:
   - Add Vitest coverage for `WEB-CAMP-001`..`WEB-CAMP-005`, verifying pure helpers, Nuxt UI slot/hygiene compliance (`SPEC 0015`), and updated navigation/leaderboard rendering.

## Interfaces

```typescript
// apps/web/app/utils/campaignSelect.ts
export function canAccessLevel(level: GameLevelSchema, session: PlayerSessionStatus): 'available' | 'pro_locked'
export function buildCategorySummaries(
  levels: GameLevelSchema[],
  session: PlayerSessionStatus
): DifficultyCategoryCardData[]
export function buildLevelTiles(
  levels: GameLevelSchema[],
  progressByLevel: Record<string, LevelProgressItem>,
  difficulty: DifficultyCategory,
  session: PlayerSessionStatus
): LevelTileItem[]
export function nextCampaignLevel(
  levels: GameLevelSchema[],
  currentLevelId: string
): GameLevelSchema | null
```

## Boundaries check

- [ ] Requires Spec `0039` API contract (`GET /game/levels`, `GET /game/leaderboard`, `GET /game/progress`) to be committed before implementing
- [ ] `apps/web` talks to the gateway only through `useShieldApi()` and `app/types/api.gen.ts`
- [ ] Strict Spec `0015` design-system hygiene and WCAG 2.1 AA/AAA contrast rules pass

## Alternatives considered

| Option | Why not |
| --- | --- |
| Multi-pane circuit map or LeetCode table with persistent sidebars | Crowds small and standard desktop viewports, reduces text/border contrast readability, and distracts from fast level entry compared to classic minimal tile grids. |
| Put all 23 tiles on one giant grid | Crowds 23 cards onto one viewport; stepping Category Cards -> `5`/`10`/`8` numbered tiles matches classic indie puzzle games and gives generous whitespace. |

## Risks and rollback

- **Spec dependency:** Spec `0040` builds directly on Spec `0039`'s OpenAPI types; do not start Spec `0040`'s SDD implementation cycle until Spec `0039` is `Implemented`.
- **Contrast regressions:** Ensure secondary text (`text-muted`) and tile borders meet `>= 4.5:1` / `>= 3.0:1` contrast by checking computed Nuxt UI dark/light tokens rather than faint `opacity-*` modifiers.
- **Hygiene regressions:** Keep `color="error"` mapped dynamically via TS helper (`WEB-UI-005`) and keep all `apps/web/app/` copy free of emojis and `\u2014` em-dashes (`WEB-UI-003`).
