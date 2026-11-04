<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { LevelId, ScoreRecord } from '~/types/api'

const { getScores } = useShieldApi()
const { secrets } = useByodSecrets()

const showDifficultySelect = ref(false)
const isSettingsOpen = ref(false)
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

onMounted(loadScoreboard)

const bestScoreFor = (levelId: LevelId): number => {
  const matching = scores.value.filter(s => s.level_id === levelId)
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
      class="mx-auto grid h-full w-full max-w-6xl grid-cols-1 lg:grid-cols-12"
    >
      <!-- Left Side: Game Main Menu -->
      <div class="flex flex-col justify-center border-b border-default p-8 lg:col-span-5 lg:border-b-0 lg:border-r">
        <div class="space-y-8">
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

          <div>
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
              label="Settings"
              icon="i-lucide-sliders-horizontal"
              color="neutral"
              variant="link"
              size="xl"
              block
              class="text-base justify-start px-0"
              @click="isSettingsOpen = true"
            />
          </div>
        </div>
      </div>

      <!-- Right Side: Leaderboard (No nested card) -->
      <div class="flex flex-col justify-center p-8 lg:col-span-7 overflow-y-auto">
        <div class="space-y-4">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <h2 class="text-base font-bold">
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
            description="Play a level and save your score."
          />
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
        <div class="flex items-center gap-3">
          <UButton
            label="Back"
            icon="i-lucide-arrow-left"
            color="neutral"
            variant="ghost"
            size="lg"
            class="text-base"
            @click="showDifficultySelect = false"
          />
          <span class="text-base font-bold uppercase tracking-wider text-highlighted">
            Select Level
          </span>
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
      </div>
    </div>

    <!-- Settings Modal (Configure Secrets + Theme Toggle) -->
    <UModal v-model:open="isSettingsOpen">
      <template #header>
        <div class="flex items-center justify-between w-full">
          <h2 class="text-base font-bold uppercase text-highlighted">
            Settings
          </h2>
        </div>
      </template>

      <template #body>
        <div class="space-y-5">
          <!-- Dark / Light Mode Toggle (left-right aligned) -->
          <UFormField
            name="theme"
            label="Theme"
            description="Dark or light mode"
            size="lg"
            orientation="horizontal"
            class="flex items-center justify-between gap-4"
          >
            <UColorModeSwitch
              color="neutral"
              size="lg"
            />
          </UFormField>

          <div class="border-t border-default pt-4 space-y-4">
            <div class="text-sm font-bold uppercase tracking-wider text-highlighted">
              Configure secrets
            </div>

            <UFormField
              name="openai_api_key"
              label="OpenAI API key"
              description="In-memory secret"
              size="lg"
              orientation="horizontal"
              class="flex items-center justify-between gap-4"
            >
              <UInput
                v-model="secrets.openai_api_key"
                type="password"
                placeholder="sk-..."
                autocomplete="off"
                size="md"
                class="w-56"
              />
            </UFormField>

            <UFormField
              name="groq_api_key"
              label="Groq API key"
              description="In-memory secret"
              size="lg"
              orientation="horizontal"
              class="flex items-center justify-between gap-4"
            >
              <UInput
                v-model="secrets.groq_api_key"
                type="password"
                placeholder="gsk_..."
                autocomplete="off"
                size="md"
                class="w-56"
              />
            </UFormField>

            <UFormField
              name="gemini_api_key"
              label="Gemini API key"
              description="In-memory secret"
              size="lg"
              orientation="horizontal"
              class="flex items-center justify-between gap-4"
            >
              <UInput
                v-model="secrets.gemini_api_key"
                type="password"
                placeholder="AIza..."
                autocomplete="off"
                size="md"
                class="w-56"
              />
            </UFormField>
          </div>
        </div>
      </template>

      <template #footer>
        <div class="flex justify-end w-full">
          <UButton
            label="Done"
            color="neutral"
            variant="solid"
            size="md"
            @click="isSettingsOpen = false"
          />
        </div>
      </template>
    </UModal>
  </div>
</template>
