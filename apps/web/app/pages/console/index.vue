<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { ScoreRecord } from '~/types/api'
import { consoleScoreStats, resolveConsoleAccess } from '~/utils/gameBoard'
import { buildPageSeo } from '~/utils/seo'

definePageMeta({
  path: '/_console',
  layout: 'dashboard'
})

const runtimeConfig = useRuntimeConfig()
useSeoMeta(buildPageSeo({
  title: 'Admin Console',
  description: 'Admin console for monitoring player scores, medal statistics, and managing the ai-shield leaderboard.',
  path: '/_console',
  siteUrl: runtimeConfig.public.siteUrl,
  noindex: true
}))

const { status } = useAdminAccess()
const { getScores, clearScores } = useShieldApi()
const toast = useToast()

const access = computed(() => resolveConsoleAccess(status.value))
const scores = ref<ScoreRecord[]>([])
// Tiles cover the 100 best current-version scores, the most the scores endpoint returns.
const stats = computed(() => consoleScoreStats(scores.value))
const statTiles = computed(() => [
  { label: 'Scores recorded', icon: 'i-lucide-trophy', value: stats.value.scores },
  { label: 'Players on the board', icon: 'i-lucide-users', value: stats.value.players },
  { label: 'Easy / Medium / Hard', icon: 'i-lucide-layers', value: `${stats.value.byLevel.easy} / ${stats.value.byLevel.medium} / ${stats.value.byLevel.hard}` },
  { label: 'Gold / Silver / Bronze', icon: 'i-lucide-medal', value: `${stats.value.medals.gold} / ${stats.value.medals.silver} / ${stats.value.medals.bronze}` }
])
const clearing = ref(false)
// Clearing the scoreboard needs a typed confirmation (spec 0053).
const isClearOpen = ref(false)
const clearConfirm = ref('')

const scoreColumns: TableColumn<ScoreRecord>[] = [
  { accessorKey: 'player_name', header: 'Player' },
  { accessorKey: 'level_id', header: 'Level' },
  { accessorKey: 'medal', header: 'Medal' },
  { accessorKey: 'total_score', header: 'Score' },
  { accessorKey: 'avg_latency_ms', header: 'Avg time (ms)' },
  { accessorKey: 'total_cost_usd', header: 'Cost ($)' }
]

const loadScores = async () => {
  if (!access.value.allowed) return
  try {
    scores.value = await getScores(undefined, 100)
  } catch (err) {
    console.warn('Could not load scores:', err)
  }
}

const handleClearScores = async () => {
  if (clearConfirm.value !== 'CLEAR') return
  clearing.value = true
  try {
    await clearScores()
    scores.value = []
    isClearOpen.value = false
    clearConfirm.value = ''
    toast.add({
      title: 'Scoreboard cleared',
      description: 'All saved scoreboard records were removed.',
      icon: 'i-lucide-check',
      color: 'neutral'
    })
  } catch {
    toast.add({
      title: 'Action denied',
      description: 'Admin access is required to clear scoreboard records.',
      icon: 'i-lucide-triangle-alert',
      color: 'neutral'
    })
  } finally {
    clearing.value = false
  }
}

// No admin data is fetched before clearance is granted (spec 0053).
watch(
  () => access.value.allowed,
  (allowed) => {
    if (allowed) void loadScores()
  },
  { immediate: true }
)
</script>

<template>
  <UDashboardPanel id="console-overview">
    <template #header>
      <UDashboardNavbar title="Admin console">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>

        <template #right>
          <UButton
            v-if="access.allowed"
            icon="i-lucide-refresh-cw"
            color="neutral"
            variant="ghost"
            square
            aria-label="Refresh scores"
            @click="loadScores()"
          />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div
        v-if="!access.allowed"
        class="py-16"
      >
        <UEmpty
          icon="i-lucide-lock"
          title="Site admin access required"
          description="Normal players cannot open /_console. Sign in with an admin account to monitor and manage the game's scores."
        >
          <template #actions>
            <UButton
              to="/game"
              label="Return to game"
              color="neutral"
              variant="outline"
            />
          </template>
        </UEmpty>
      </div>

      <div
        v-else
        class="space-y-8"
      >
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <UPageCard
            v-for="tile in statTiles"
            :key="tile.label"
            :icon="tile.icon"
            :title="String(tile.value)"
            :description="tile.label"
            variant="subtle"
          />
        </div>

        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <div>
              <h2 class="text-base font-semibold text-highlighted">
                Scoreboard management
              </h2>
              <p class="text-sm text-muted">
                Review or reset player records stored in the gateway database.
              </p>
            </div>

            <UButton
              v-if="scores.length > 0"
              label="Clear scoreboard"
              icon="i-lucide-trash-2"
              color="error"
              variant="outline"
              size="sm"
              @click="isClearOpen = true"
            />
          </div>

          <UTable
            v-if="scores.length > 0"
            :data="scores"
            :columns="scoreColumns"
          />
          <UEmpty
            v-else
            icon="i-lucide-trophy"
            title="No saved scores"
            description="Player runs submitted from /game will appear here."
          />
        </div>
      </div>

      <UModal
        v-model:open="isClearOpen"
        title="Clear scoreboard"
        description="This deletes every score on the leaderboard. It cannot be undone."
      >
        <template #body>
          <UFormField
            label="Type CLEAR to confirm"
            name="confirm"
          >
            <UInput
              v-model="clearConfirm"
              autocomplete="off"
              class="w-full"
            />
          </UFormField>
        </template>

        <template #footer>
          <div class="flex w-full justify-end gap-2">
            <UButton
              label="Cancel"
              color="neutral"
              variant="ghost"
              @click="isClearOpen = false"
            />
            <UButton
              label="Clear scoreboard"
              color="error"
              :loading="clearing"
              :disabled="clearConfirm !== 'CLEAR'"
              @click="handleClearScores"
            />
          </div>
        </template>
      </UModal>
    </template>
  </UDashboardPanel>
</template>
