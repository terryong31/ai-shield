<script setup lang="ts">
import type { TableColumn, ToggleGroupItem } from '@nuxt/ui'
import type {
  DifficultyCategory,
  DifficultyLeaderboardEntry,
  GameLevelSchema,
  LevelId,
  LevelProgressItem
} from '~/types/api'
import {
  FALLBACK_CAMPAIGN_LEVELS,
  buildCategorySummaries,
  buildLevelTiles,
  difficultyBadgeColor,
  type DifficultyCategoryCardData,
  type LevelTileItem
} from '~/utils/campaignSelect'
import { customModeAccess } from '~/utils/customSandbox'
import { leaderboardRows, type LeaderboardRow } from '~/utils/leaderboard'
import { TWITTER_CARD_ALT, TWITTER_CARD_PATH, resolveSiteUrl } from '~/utils/seo'

const route = useRoute()
const router = useRouter()
const { getLevels, getProgress } = useShieldApi()

const {
  difficultyLeaderboards,
  myRanks,
  hasLoaded,
  loading: loadingScores,
  selectedDifficulty: selectedLeaderboardDifficulty,
  refreshScores,
  refreshMyRank,
  prefetchScores,
  startPolling,
  stopPolling
} = useLeaderboard()

const {
  session,
  isAnonymous,
  isLoggedIn,
  isPaid,
  loadingAuth,
  refreshSession,
  continueAnonymously,
  signOutPlayer
} = usePlayerAuth()

const levels = ref<GameLevelSchema[]>(FALLBACK_CAMPAIGN_LEVELS)
const progressByLevel = ref<Record<string, LevelProgressItem>>({})

const parseDifficultyParam = (raw: unknown): DifficultyCategory | null => {
  const norm = String(raw || '').trim().toLowerCase()
  if (norm === 'easy') return 'Easy'
  if (norm === 'medium') return 'Medium'
  if (norm === 'hard') return 'Hard'
  return null
}

const showLevelSelect = ref(
  route.query.view === 'levels' || parseDifficultyParam(route.query.difficulty) !== null
)
const activeDifficulty = ref<DifficultyCategory | null>(
  parseDifficultyParam(route.query.difficulty)
)

watch(
  () => [route.query.view, route.query.difficulty],
  ([view, diff]) => {
    const parsedDiff = parseDifficultyParam(diff)
    if (view === 'levels' || parsedDiff !== null) {
      showLevelSelect.value = true
      activeDifficulty.value = parsedDiff
    } else if (view === undefined && diff === undefined) {
      showLevelSelect.value = false
      activeDifficulty.value = null
    }
  }
)

const openStepOne = () => {
  showLevelSelect.value = true
  activeDifficulty.value = null
  void router.replace({ query: { view: 'levels' } })
}

const backToMainMenu = () => {
  showLevelSelect.value = false
  activeDifficulty.value = null
  void router.replace({ query: {} })
}

const isUpgradeModalOpen = ref(false)
const upgradeTargetTitle = ref('Pro Campaign Level')
const isBriefingModalOpen = ref(false)
const selectedTile = ref<LevelTileItem | null>(null)

const categoryCards = computed(() =>
  buildCategorySummaries(levels.value, session.value)
)

const activeLevelTiles = computed(() =>
  activeDifficulty.value
    ? buildLevelTiles(levels.value, progressByLevel.value, activeDifficulty.value, session.value)
    : []
)

const handleSelectCategory = (card: DifficultyCategoryCardData) => {
  if (card.locked) {
    upgradeTargetTitle.value = `${card.title} Difficulty Campaign`
    isUpgradeModalOpen.value = true
    return
  }
  showLevelSelect.value = true
  activeDifficulty.value = card.difficulty
  void router.replace({
    query: { view: 'levels', difficulty: card.slug }
  })
}

const handleSelectTile = (tile: LevelTileItem) => {
  if (tile.locked) {
    upgradeTargetTitle.value = `${tile.kicker}: ${tile.title}`
    isUpgradeModalOpen.value = true
    return
  }
  selectedTile.value = tile
  isBriefingModalOpen.value = true
}

const runtimeConfig = useRuntimeConfig()
const siteUrl = computed(() => resolveSiteUrl(runtimeConfig.public.siteUrl))
const seoTitle = computed(() => {
  if (!showLevelSelect.value) return 'Prompt Injection Defence Game'
  if (activeDifficulty.value) return `Select Level · ${activeDifficulty.value}`
  return 'Select Difficulty'
})
const seoDescription = 'Wire layered security checks on a visual board to protect AI agents from prompt injection waves, Base64 jailbreaks, and unauthorized tool calls. Compete on the live leaderboard.'

useSeoMeta({
  title: () => seoTitle.value,
  description: seoDescription,
  ogTitle: () => `${seoTitle.value} | ai-shield`,
  ogDescription: seoDescription,
  ogType: 'website',
  ogSiteName: 'ai-shield',
  ogUrl: () => `${siteUrl.value}/`,
  ogImage: () => `${siteUrl.value}${TWITTER_CARD_PATH}`,
  ogImageAlt: TWITTER_CARD_ALT,
  ogImageWidth: 1200,
  ogImageHeight: 630,
  twitterCard: 'summary_large_image',
  twitterTitle: () => `${seoTitle.value} | ai-shield`,
  twitterDescription: seoDescription,
  twitterImage: () => `${siteUrl.value}${TWITTER_CARD_PATH}`,
  twitterImageAlt: TWITTER_CARD_ALT,
  robots: 'index, follow'
})

const ensureSession = async () => {
  await refreshSession()
  if (!session.value.authenticated) {
    await continueAnonymously()
  }
}

const loadCatalogAndProgress = async () => {
  const [catalogRes, progressRes] = await Promise.allSettled([
    getLevels(),
    getProgress()
  ])
  if (catalogRes.status === 'fulfilled' && catalogRes.value.levels.length > 0) {
    levels.value = catalogRes.value.levels
  }
  if (progressRes.status === 'fulfilled') {
    const mapped: Record<string, LevelProgressItem> = {}
    for (const item of progressRes.value.levels) {
      mapped[item.level_id] = item
    }
    progressByLevel.value = mapped
  }
}

onServerPrefetch(async () => {
  if (!showLevelSelect.value) await prefetchScores()
})

watch(() => isLoggedIn.value && session.value.player_name, (player) => {
  if (player) void refreshMyRank(selectedLeaderboardDifficulty.value)
})

onMounted(async () => {
  if (showLevelSelect.value) {
    await Promise.all([
      loadCatalogAndProgress(),
      ensureSession()
    ])
    startPolling()
    void refreshScores({ background: true })
    return
  }

  await Promise.all([
    refreshScores({ background: hasLoaded.value }),
    ensureSession()
  ])
  startPolling()
  void loadCatalogAndProgress()
})

watch(hasLoaded, (loaded) => {
  if (loaded && !session.value.authenticated) {
    void ensureSession()
  }
})

onBeforeUnmount(() => {
  stopPolling()
})

const bestScoreFor = (levelId: LevelId): number => {
  const fromProgress = progressByLevel.value[levelId]?.best_score
  return typeof fromProgress === 'number' && fromProgress > 0 ? fromProgress : 0
}

const leaderboardToggleItems: ToggleGroupItem[] = (['Easy', 'Medium', 'Hard'] as const).map(
  difficulty => ({ label: difficulty, value: difficulty })
)

// Reka's single toggle group emits an empty value when the active item is clicked again; keep a selection.
const leaderboardToggle = computed({
  get: () => selectedLeaderboardDifficulty.value,
  set: (value: unknown) => {
    if (value === 'Easy' || value === 'Medium' || value === 'Hard') selectedLeaderboardDifficulty.value = value
  }
})

const filteredScores = computed<DifficultyLeaderboardEntry[]>(() =>
  difficultyLeaderboards.value[selectedLeaderboardDifficulty.value] ?? []
)

const activeMyRank = computed(() => myRanks.value[selectedLeaderboardDifficulty.value] ?? null)

const boardRows = computed(() => leaderboardRows(filteredScores.value, activeMyRank.value, session.value))

// Sticky keeps the row on the bottom edge until its own place in the list scrolls into view.
const OWN_ROW_CLASS = 'sticky bottom-0 z-1 bg-inverted [&>td]:py-2.5'

const leaderboardTableMeta = {
  class: {
    tr: (row: { original: LeaderboardRow }) => row.original.own ? OWN_ROW_CLASS : ''
  }
}

const scoreColumns: TableColumn<LeaderboardRow>[] = [
  { id: 'rank', header: 'Rank', meta: { class: { th: 'w-16 pr-0', td: 'w-16 pr-0' } } },
  { accessorKey: 'player_name', header: 'Player' },
  { accessorKey: 'total_score', header: 'Total Score', meta: { class: { th: 'text-right', td: 'text-right' } } }
]
</script>

<template>
  <main class="flex h-dvh w-screen overflow-hidden bg-default text-default text-base">
    <!-- View 1: Main Menu + Difficulty Leaderboard -->
    <div
      v-if="!showLevelSelect"
      class="grid h-full w-full grid-cols-1 lg:grid-cols-10"
    >
      <!-- Left Side: Game Main Menu (30%) -->
      <div class="relative z-10 flex flex-col justify-center border-b border-default bg-default p-8 lg:col-span-3 lg:border-b-0 lg:border-r lg:px-10">
        <div class="mx-auto w-full max-w-xs space-y-8">
          <div class="space-y-2">
            <div class="flex items-center gap-2.5">
              <h1 class="text-3xl font-bold tracking-tight text-highlighted">
                ai-shield
              </h1>
            </div>
            <p class="text-sm text-muted">
              Prompt injection defence game
            </p>
          </div>

          <div class="space-y-1">
            <UButton
              label="Play Game"
              icon="i-lucide-play"
              color="neutral"
              variant="link"
              size="xl"
              block
              class="text-base justify-start px-0"
              @click="openStepOne"
            />

            <UButton
              v-if="isAnonymous"
              to="/auth/login"
              label="Sign in / Create account"
              icon="i-lucide-user"
              color="neutral"
              variant="link"
              size="xl"
              block
              class="text-base justify-start px-0"
            />

            <UButton
              v-if="isLoggedIn"
              :label="isPaid ? 'Manage Plan' : 'Upgrade Plan'"
              icon="i-lucide-sparkles"
              color="neutral"
              variant="link"
              size="xl"
              block
              to="/plans"
              class="text-base justify-start px-0"
            />

            <UButton
              to="/settings"
              label="Settings"
              icon="i-lucide-sliders-horizontal"
              color="neutral"
              variant="link"
              size="xl"
              block
              class="text-base justify-start px-0"
            />

            <UButton
              v-if="isLoggedIn"
              label="Sign out"
              icon="i-lucide-log-out"
              color="neutral"
              variant="link"
              size="xl"
              block
              :loading="loadingAuth"
              class="text-base justify-start px-0"
              @click="signOutPlayer"
            />
          </div>
        </div>
      </div>

      <!-- Right Side: Difficulty Leaderboard (70%) -->
      <div class="relative flex flex-col items-center justify-center overflow-y-auto bg-elevated/25 p-8 lg:col-span-7">
        <div
          class="pointer-events-none absolute inset-0 overflow-hidden"
          aria-hidden="true"
        >
          <div class="absolute inset-0 bg-[linear-gradient(to_right,var(--ui-border)_1px,transparent_1px),linear-gradient(to_bottom,var(--ui-border)_1px,transparent_1px)] bg-[size:40px_40px] opacity-40 [mask-image:radial-gradient(ellipse_75%_65%_at_50%_50%,#000_25%,transparent_100%)]" />
          <div class="absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_50%_50%,color-mix(in_oklab,var(--ui-border-accented)_24%,transparent),transparent_75%)]" />
        </div>

        <div class="relative z-10 mx-auto w-full max-w-2xl space-y-4">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <h2 class="text-base font-bold text-highlighted">
                Leaderboard
              </h2>
            </div>

            <UToggleGroup
              v-model="leaderboardToggle"
              :items="leaderboardToggleItems"
              attached
              variant="outline"
              active-variant="solid"
              active-color="neutral"
              size="sm"
            />
          </div>

          <div class="overflow-hidden rounded-lg border border-default bg-default/90 shadow-sm backdrop-blur-md">
            <UTable
              class="max-h-96"
              sticky="header"
              :data="boardRows"
              :columns="scoreColumns"
              :meta="leaderboardTableMeta"
              :loading="loadingScores && !hasLoaded"
              :empty="hasLoaded ? 'No scores yet' : 'Loading...'"
              loading-color="neutral"
              loading-animation="carousel"
            >
              <template #loading>
                <span class="text-sm text-muted">Loading...</span>
              </template>

              <template #rank-cell="{ row }">
                <span
                  class="text-sm tabular-nums"
                  :class="row.original.own ? 'text-inverted' : 'text-muted'"
                >
                  {{ row.original.rankLabel }}
                </span>
              </template>

              <template #player_name-cell="{ row }">
                <span
                  class="text-sm"
                  :class="row.original.own ? 'text-inverted' : 'text-highlighted'"
                >
                  {{ row.original.player_name }}
                </span>
              </template>

              <template #total_score-cell="{ row }">
                <span
                  class="text-sm font-semibold tabular-nums"
                  :class="row.original.own ? 'text-inverted' : 'text-highlighted'"
                >
                  {{ row.original.total_score }}
                </span>
              </template>
            </UTable>
          </div>
        </div>
      </div>
    </div>

    <!-- View 2, Step 1: Minimal Monochrome Difficulty Category Select (/?view=levels) -->
    <div
      v-else-if="!activeDifficulty"
      class="mx-auto flex h-full w-full max-w-5xl flex-col justify-center overflow-y-auto px-6 py-8"
    >
      <div class="w-full space-y-6">
        <!-- Minimal Header: Back + Centered Select Difficulty -->
        <div class="grid grid-cols-3 items-center">
          <div class="flex items-center">
            <UButton
              label="Back"
              icon="i-lucide-arrow-left"
              color="neutral"
              variant="link"
              size="xl"
              class="px-0"
              @click="backToMainMenu"
            />
          </div>

          <h1 class="text-center text-lg font-bold tracking-tight text-highlighted">
            Select Difficulty
          </h1>
        </div>

        <!-- 3 Spacious Vertical UPageCard Poster Cards (Easy 5, Medium 10, Hard 8) -->
        <div class="grid grid-cols-1 gap-5 md:grid-cols-3">
          <UPageCard
            v-for="card in categoryCards"
            :key="card.difficulty"
            variant="outline"
            role="button"
            tabindex="0"
            :aria-label="card.locked ? `${card.title} (${card.levelsCount} levels, Pro locked)` : `${card.title} (${card.levelsCount} levels)`"
            :ui="{
              root: 'group relative min-h-88 rounded-2xl transition-transform duration-200 ease-out will-change-transform hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inverted',
              container: 'flex lg:flex h-full w-full flex-1 flex-col p-6 sm:p-7',
              wrapper: 'flex h-full w-full flex-1 flex-col items-stretch',
              body: 'flex h-full w-full flex-1 flex-col'
            }"
            @click="handleSelectCategory(card)"
            @keydown.enter.prevent="handleSelectCategory(card)"
            @keydown.space.prevent="handleSelectCategory(card)"
          >
            <div
              class="flex h-full w-full flex-1 flex-col justify-between"
              :class="card.locked ? 'blur-sm opacity-35 select-none pointer-events-none' : ''"
            >
              <!-- Top Row: Clean Index + Single Difficulty Pill -->
              <div class="flex w-full items-center justify-between gap-2">
                <span class="text-xs font-medium text-muted">
                  {{ card.indexLabel }}
                </span>
                <UBadge
                  :label="card.difficulty"
                  :color="card.badgeColor"
                  variant="subtle"
                  size="sm"
                />
              </div>

              <!-- Center Emblem: Generous Negative Space -->
              <div class="my-auto flex w-full items-center justify-center py-8">
                <div
                  class="flex size-20 items-center justify-center rounded-full border border-default bg-elevated/40 transform-gpu will-change-transform transition-transform duration-200 ease-out"
                  :class="card.locked ? '' : 'group-hover:scale-105'"
                >
                  <UIcon
                    :name="card.icon"
                    class="size-8 text-highlighted"
                  />
                </div>
              </div>

              <!-- Bottom Stack: Bold Title + 1-Line Subtitle + Inline Enter Cue -->
              <div class="w-full space-y-3">
                <div class="space-y-1 text-left">
                  <h2 class="text-2xl font-bold tracking-tight text-highlighted">
                    {{ card.title }}
                  </h2>
                  <p class="text-sm text-muted">
                    {{ card.subtitle }}
                  </p>
                </div>

                <div
                  v-if="!card.locked"
                  class="flex w-full items-center justify-end gap-1.5 pt-1 text-xs font-semibold text-muted transition-colors group-hover:text-highlighted"
                >
                  <span>Enter</span>
                  <UIcon
                    name="i-lucide-arrow-right"
                    class="size-3.5 transition-transform duration-200 ease-out group-hover:translate-x-0.5"
                  />
                </div>
              </div>
            </div>

            <!-- Centered Padlock Overlay on Locked Pro Card -->
            <div
              v-if="card.locked"
              class="pointer-events-none absolute inset-0 z-10 flex items-center justify-center"
            >
              <div class="flex size-14 items-center justify-center rounded-full border border-accented bg-elevated/95 text-highlighted shadow-lg">
                <UIcon
                  name="i-lucide-lock"
                  class="size-6"
                />
              </div>
            </div>
          </UPageCard>
        </div>

        <!-- Custom Sandbox Strip (spec 0022) -->
        <UCard
          v-if="customModeAccess(session) !== 'hidden'"
          variant="outline"
          :ui="{ body: 'flex flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6 sm:py-6' }"
        >
          <div class="flex items-center gap-5">
            <div class="flex size-18 shrink-0 items-center justify-center rounded-full border border-default bg-elevated/50">
              <UIcon
                name="i-lucide-sliders-horizontal"
                class="size-7 text-highlighted"
              />
            </div>
            <div class="space-y-0.5">
              <div class="flex items-center gap-2">
                <h2 class="text-xl font-bold text-highlighted">
                  Custom Sandbox
                </h2>
              </div>
              <p class="text-sm text-muted">
                Test a defence board against your own agent objective, tools, prompt dataset, and model API key.
              </p>
            </div>
          </div>

          <UButton
            v-if="customModeAccess(session) === 'available'"
            to="/game?level=custom"
            label="Open Sandbox"
            icon="i-lucide-play"
            trailing-icon="i-lucide-arrow-right"
            color="neutral"
            variant="outline"
            size="md"
          />
          <UButton
            v-else
            to="/plans"
            label="Upgrade to Paid"
            icon="i-lucide-lock"
            trailing-icon="i-lucide-arrow-right"
            color="neutral"
            variant="outline"
            size="md"
          />
        </UCard>
      </div>
    </div>

    <!-- View 2, Step 2: Minimal Level Tile Grid (/?view=levels&difficulty=easy|medium|hard) -->
    <div
      v-else
      class="mx-auto flex h-full w-full max-w-5xl flex-col justify-center overflow-y-auto px-6 py-8"
    >
      <div class="w-full space-y-6">
        <!-- Minimal Header Only: Back + Centered Select Level + Difficulty Badge -->
        <div class="grid grid-cols-3 items-center">
          <div class="flex items-center">
            <UButton
              label="Back"
              icon="i-lucide-arrow-left"
              color="neutral"
              variant="link"
              size="xl"
              class="px-0"
              @click="openStepOne"
            />
          </div>

          <div class="flex items-center justify-center gap-2.5">
            <h1 class="text-lg font-bold tracking-tight text-highlighted">
              Select Level
            </h1>
            <UBadge
              :label="activeDifficulty"
              :color="difficultyBadgeColor(activeDifficulty)"
              variant="subtle"
              size="sm"
            />
          </div>

          <div />
        </div>

        <!-- Centered Spacious Tile Grid (5 on Easy, 5x2 on Medium, 4x2 on Hard) -->
        <div
          class="grid gap-3.5"
          :class="activeDifficulty === 'Hard' ? 'grid-cols-2 sm:grid-cols-4' : 'grid-cols-2 sm:grid-cols-3 md:grid-cols-5'"
        >
          <UCard
            v-for="lvl in activeLevelTiles"
            :key="lvl.id"
            variant="outline"
            role="button"
            tabindex="0"
            :aria-label="lvl.locked ? `${lvl.kicker}: ${lvl.title} (Pro locked)` : `${lvl.kicker}: ${lvl.title}, High score ${bestScoreFor(lvl.id).toLocaleString()}`"
            :ui="{
              root: 'group relative cursor-pointer rounded-xl transition-[transform,border-color] duration-150 ease-out will-change-transform hover:-translate-y-0.5 hover:border-accented focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inverted',
              body: 'flex min-h-44 flex-col justify-between p-4 sm:p-4'
            }"
            @click="handleSelectTile(lvl)"
            @keydown.enter.prevent="handleSelectTile(lvl)"
            @keydown.space.prevent="handleSelectTile(lvl)"
          >
            <!-- Tile Interior (Blurred when Pro-locked) -->
            <div
              class="flex h-full flex-col justify-between gap-3"
              :class="lvl.locked ? 'blur-[4px] opacity-35 select-none pointer-events-none' : ''"
            >
              <!-- Top Row: Level Kicker + Cleared Check -->
              <div class="flex items-center justify-between gap-1.5">
                <span class="text-xs font-medium text-muted">
                  {{ lvl.kicker }}
                </span>
                <UIcon
                  v-if="lvl.won"
                  name="i-lucide-circle-check"
                  class="size-4 shrink-0 text-highlighted"
                />
              </div>

              <!-- Center: Stage Number + Level Title -->
              <div class="my-auto flex flex-col items-center justify-center py-2 text-center">
                <span class="text-3xl font-bold tracking-tight tabular-nums text-highlighted">
                  {{ lvl.stageNumber }}
                </span>
                <h2 class="mt-1 line-clamp-1 text-xs font-medium text-muted group-hover:text-default">
                  {{ lvl.title }}
                </h2>
                <span class="sr-only">
                  High score {{ bestScoreFor(lvl.id).toLocaleString() }}
                </span>
              </div>

              <!-- Footer: Centered 3-Star UInputRating -->
              <div class="flex items-center justify-center border-t border-default/60 pt-2.5">
                <UInputRating
                  :model-value="lvl.stars"
                  :length="3"
                  readonly
                  color="warning"
                  size="sm"
                  :aria-label="`${lvl.stars} of 3 stars`"
                />
              </div>
            </div>

            <!-- Centered Padlock Overlay on Pro-Locked Tile -->
            <div
              v-if="lvl.locked"
              class="pointer-events-none absolute inset-0 z-10 flex items-center justify-center"
            >
              <div class="flex size-10 items-center justify-center rounded-full border border-accented bg-elevated/95 text-highlighted shadow-md">
                <UIcon
                  name="i-lucide-lock"
                  class="size-4"
                />
              </div>
            </div>
          </UCard>
        </div>
      </div>
    </div>

    <footer class="flex justify-center py-4 text-xs">
      <ULink
        to="/privacy"
        class="text-muted"
      >
        Privacy Policy
      </ULink>
    </footer>

    <!-- Mission Briefing & Upgrade to Pro Modals -->
    <CampaignLevelBriefingModal
      v-model:open="isBriefingModalOpen"
      :level="selectedTile?.level ?? null"
      :stage-number="selectedTile?.stageNumber ?? '01'"
      :stars="selectedTile?.stars ?? 0"
      :best-score="selectedTile ? bestScoreFor(selectedTile.id) : 0"
      :won="selectedTile?.won ?? false"
      :mastered="selectedTile?.mastered ?? false"
    />

    <CampaignUpgradeProModal
      v-model:open="isUpgradeModalOpen"
      :target-title="upgradeTargetTitle"
    />
  </main>
</template>
