<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { ScoreRecord } from '~/types/api'
import { resolveConsoleAccess } from '~/utils/gameBoard'

definePageMeta({
  path: '/_console',
  layout: 'dashboard'
})

const { status, openModal } = usePassphrase()
const { getScores, clearScores } = useShieldApi()
const toast = useToast()

const access = computed(() => resolveConsoleAccess(status.value))
const stats = useTemplateRef('stats')
const scores = ref<ScoreRecord[]>([])
const clearing = ref(false)

const scoreColumns: TableColumn<ScoreRecord>[] = [
  { accessorKey: 'player_name', header: 'Player' },
  { accessorKey: 'level_id', header: 'Level' },
  { accessorKey: 'medal', header: 'Medal' },
  { accessorKey: 'total_score', header: 'Score' },
  { accessorKey: 'avg_latency_ms', header: 'Avg time (ms)' },
  { accessorKey: 'total_cost_usd', header: 'Cost ($)' }
]

const loadScores = async () => {
  try {
    scores.value = await getScores(undefined, 50)
  } catch (err) {
    console.warn('Could not load scores:', err)
  }
}

const handleClearScores = async () => {
  clearing.value = true
  try {
    await clearScores()
    scores.value = []
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

onMounted(loadScores)
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
            aria-label="Refresh stats"
            @click="stats?.refresh(); loadScores()"
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
          description="Normal players cannot open /_console. Enter the admin passphrase to manage scores, logs, and settings."
        >
          <template #actions>
            <UButton
              label="Enter admin passphrase"
              icon="i-lucide-key-round"
              color="neutral"
              variant="solid"
              @click="openModal"
            />
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
        <DashboardStats ref="stats" />
        <DashboardPipeline />

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
              :loading="clearing"
              @click="handleClearScores"
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
    </template>
  </UDashboardPanel>
</template>
