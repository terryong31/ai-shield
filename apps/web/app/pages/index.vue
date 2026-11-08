<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { LevelId, ScoreRecord } from '~/types/api'
import { customModeAccess } from '~/utils/customSandbox'
import { formatQuotaSummary } from '~/utils/gameBoard'

const { getScores } = useShieldApi()
const {
  session,
  isAnonymous,
  isLoggedIn,
  isPaid,
  loadingAuth,
  refreshSession,
  continueAnonymously,
  upgradeToPaid,
  signOutPlayer
} = usePlayerAuth()

const showDifficultySelect = ref(false)
const selectedLeaderboardTab = ref<LevelId>('easy')
const scores = ref<ScoreRecord[]>([])
const loadingScores = ref(false)

const difficulties: Array<{
  id: LevelId
  levelLabel: string
  difficulty: 'Easy' | 'Medium' | 'Hard'
  title: string
  description: string
  color: 'success' | 'warning' | 'error'
}> = [
  {
    id: 'easy',
    levelLabel: 'Level One',
    difficulty: 'Easy',
    title: 'Public Helpdesk',
    description: 'The public support desk. You will be defending the store coupon system against direct prompt overrides while letting customer questions through.',
    color: 'success'
  },
  {
    id: 'medium',
    levelLabel: 'Level Two',
    difficulty: 'Medium',
    title: 'HR Handbook Assistant',
    description: 'The HR desk. You will be defending private employee salary records against hidden Base64 tricks and roleplay jailbreaks.',
    color: 'warning'
  },
  {
    id: 'hard',
    levelLabel: 'Level Three',
    difficulty: 'Hard',
    title: 'Production Operations',
    description: 'The production operations desk. You will be defending the payroll database and SQL tools against indirect injections and unauthorized tool calls.',
    color: 'error'
  }
]

const loadScoreboard = async () => {
  loadingScores.value = true
  try {
    scores.value = await getScores(undefined, 50)
  } catch (err) {
    console.warn('Scoreboard unavailable:', err)
  } finally {
    loadingScores.value = false
  }
}

onMounted(async () => {
  await refreshSession()
  if (!session.value.authenticated) {
    await continueAnonymously()
  }
  await loadScoreboard()
})

const bestScoreFor = (levelId: LevelId): number => {
  if (isAnonymous.value) return 0
  const matching = scores.value.filter(
    s => s.level_id === levelId && s.player_name === session.value.player_name
  )
  if (matching.length === 0) return 0
  return Math.max(...matching.map(s => s.total_score))
}

const filteredScores = computed(() =>
  scores.value.filter(s => s.level_id === selectedLeaderboardTab.value)
)

const scoreColumns: TableColumn<ScoreRecord>[] = [
  { accessorKey: 'player_name', header: 'Player' },
  { accessorKey: 'total_score', header: 'Score' },
  { accessorKey: 'avg_latency_ms', header: 'Speed' },
  { accessorKey: 'total_cost_usd', header: 'Cost' }
]
</script>

<template>
  <div class="flex h-dvh w-screen overflow-hidden bg-default text-default text-base">
    <!-- View 1: Main Menu + Leaderboard -->
    <div
      v-if="!showDifficultySelect"
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
              <UBadge
                v-if="!isAnonymous"
                :label="session.tier.toUpperCase()"
                color="neutral"
                variant="outline"
                size="sm"
              />
            </div>
            <p class="text-sm text-muted">
              Prompt injection defence game
            </p>
            <p
              v-if="formatQuotaSummary(session)"
              class="text-xs text-dimmed"
            >
              {{ formatQuotaSummary(session) }}
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
              @click="showDifficultySelect = true"
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
              v-if="isLoggedIn && !isPaid"
              label="Upgrade to Paid"
              icon="i-lucide-sparkles"
              color="neutral"
              variant="link"
              size="xl"
              block
              :loading="loadingAuth"
              class="text-base justify-start px-0"
              @click="upgradeToPaid"
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

      <!-- Right Side: Leaderboard (70%) -->
      <div class="scoreboard-arena relative flex flex-col items-center justify-center overflow-y-auto p-8 lg:col-span-7">
        <div
          class="scoreboard-arena-bg pointer-events-none absolute inset-0 overflow-hidden"
          aria-hidden="true"
        >
          <div class="scoreboard-grid" />
          <div class="scoreboard-orb scoreboard-orb-1" />
          <div class="scoreboard-orb scoreboard-orb-2" />
          <div class="scoreboard-scanline" />
        </div>

        <div class="relative z-10 mx-auto w-full max-w-2xl space-y-4">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <h2 class="text-base font-bold text-highlighted">
                Leaderboard
              </h2>
            </div>

            <div class="flex items-center gap-1.5">
              <UButton
                v-for="tab in (['easy', 'medium', 'hard'] as const)"
                :key="tab"
                :label="tab.split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')"
                color="neutral"
                :variant="selectedLeaderboardTab === tab ? 'solid' : 'outline'"
                size="sm"
                class="text-sm"
                @click="selectedLeaderboardTab = tab"
              />
            </div>
          </div>

          <div class="rounded-lg border border-default bg-default/85 backdrop-blur-md">
            <UTable
              v-if="filteredScores.length > 0"
              :data="filteredScores"
              :columns="scoreColumns"
            >
              <template #total_score-cell="{ row }">
                <span class="text-sm font-semibold tabular-nums text-highlighted">
                  {{ row.original.total_score.toLocaleString() }}
                </span>
              </template>

              <template #avg_latency_ms-cell="{ row }">
                <span class="text-sm tabular-nums text-muted">
                  {{ row.original.avg_latency_ms.toFixed(1) }} ms
                </span>
              </template>

              <template #total_cost_usd-cell="{ row }">
                <span class="text-sm tabular-nums text-muted">
                  ${{ row.original.total_cost_usd.toFixed(4) }}
                </span>
              </template>
            </UTable>

            <UEmpty
              v-else
              icon="i-lucide-trophy"
              title="No scores yet"
              description="Sign in and complete a level to record your score on the leaderboard."
              class="border-0 bg-transparent"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- View 2: Full-Page Level Selection (Level One, Level Two, Level Three) -->
    <div
      v-else
      class="mx-auto flex h-full w-full max-w-6xl flex-col justify-center p-8 overflow-y-auto"
    >
      <div class="space-y-6">
        <!-- Upper-Left Back Button above the cards -->
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <UButton
              label="Back"
              icon="i-lucide-arrow-left"
              color="neutral"
              variant="link"
              size="xl"
              class="text-base"
              @click="showDifficultySelect = false"
            />
            <span class="text-base font-bold uppercase tracking-wider text-highlighted">
              Select Level
            </span>
          </div>
        </div>

        <!-- Three Level Cards across the page -->
        <div class="grid grid-cols-1 gap-6 md:grid-cols-3">
          <UCard
            v-for="lvl in difficulties"
            :key="lvl.id"
            variant="outline"
            :ui="{ root: 'flex flex-col', body: 'flex-1 flex flex-col justify-between p-4 sm:p-6' }"
          >
            <template #header>
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm font-bold uppercase tracking-wider text-highlighted">
                  {{ lvl.levelLabel }}
                </span>
                <UBadge
                  :label="lvl.difficulty"
                  :color="lvl.color"
                  variant="subtle"
                  size="sm"
                  class="text-xs"
                />
              </div>
            </template>

            <div class="space-y-2">
              <h3 class="text-lg font-bold text-highlighted">
                {{ lvl.title }}
              </h3>

              <p class="text-sm leading-relaxed text-muted">
                {{ lvl.description }}
              </p>
            </div>

            <div class="pt-6 flex items-center justify-between text-sm tabular-nums">
              <span class="text-dimmed">High score</span>
              <span class="font-bold text-highlighted">
                {{ bestScoreFor(lvl.id).toLocaleString() }}
              </span>
            </div>

            <template #footer>
              <UButton
                :to="`/game?level=${lvl.id}`"
                label="Play"
                trailing-icon="i-lucide-arrow-right"
                leading-icon="i-lucide-play"
                color="neutral"
                variant="solid"
                size="xl"
                block
              />
            </template>
          </UCard>
        </div>

        <!-- Custom sandbox (spec 0022): paid players bring their own agent, dataset and key -->
        <UCard
          v-if="customModeAccess(session) !== 'hidden'"
          variant="outline"
          :ui="{ body: 'flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-6' }"
        >
          <div class="space-y-1">
            <div class="flex items-center gap-2">
              <span class="text-sm font-bold uppercase tracking-wider text-highlighted">
                Custom
              </span>
              <UBadge
                label="Paid"
                color="neutral"
                variant="outline"
                size="sm"
              />
            </div>
            <p class="text-sm text-muted">
              Defend your own agent: bring your prompts (CSV) and your own model key. Sandbox runs are not ranked.
            </p>
          </div>
          <UButton
            v-if="customModeAccess(session) === 'available'"
            to="/game?level=custom"
            label="Open sandbox"
            trailing-icon="i-lucide-arrow-right"
            color="neutral"
            variant="solid"
            size="lg"
          />
          <UButton
            v-else
            label="Upgrade to Paid"
            icon="i-lucide-lock"
            color="neutral"
            variant="outline"
            size="lg"
            :loading="loadingAuth"
            @click="upgradeToPaid"
          />
        </UCard>
      </div>
    </div>
  </div>
</template>
