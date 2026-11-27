<!-- Run results, the briefing, the score breakdown and a result cell's prompts (spec 0055). State comes from useGamePage. -->
<script setup lang="ts">
import { canAccessLevel } from '~/utils/campaignSelect'
import { breakdownStats, promptGroups, scoreBreakdown, stopSummary, waveOutcomeSummary, waveStars } from '~/utils/gameBoard'

const {
  breakdownAccordionItems,
  currentLevel,
  currentLevelId,
  highScore,
  highStars,
  isBreakdownOpen,
  isBriefingOpen,
  isResultCellOpen,
  isResultsOpen,
  newRecord,
  nextLevel,
  nodeLabel,
  openResultCell,
  resultCells,
  runStop,
  selectedResultCell,
  session,
  traces,
  waveScore
} = useGameContext()
</script>

<template>
  <!-- Run Results Modal: stars and score of the last wave (WEB-AGENT-020) -->
  <UModal
    v-model:open="isResultsOpen"
    title="Run results"
    :ui="{ content: 'sm:max-w-2xl' }"
  >
    <template #body>
      <div class="space-y-8">
        <div
          v-if="waveScore"
          class="flex flex-col items-center gap-3 text-center"
        >
          <UInputRating
            :model-value="waveStars(waveScore)"
            :length="3"
            readonly
            color="warning"
            size="xl"
            :aria-label="`${waveStars(waveScore)} of 3 stars`"
          />
          <div class="space-y-1">
            <p class="text-4xl font-bold tabular-nums text-highlighted">
              {{ waveScore.total_score.toLocaleString() }}
            </p>
            <div class="flex flex-col items-center justify-center gap-2">
              <div v-if="waveScore.won">
                <p class="font-bold text-xl py-1">
                  Victory
                </p>
              </div>
              <div v-if="waveScore.won === false">
                <p class="font-bold text-xl py-1">
                  Defeat
                </p>
              </div>
            </div>
            <p
              v-if="runStop"
              class="text-xs text-muted"
            >
              {{ stopSummary(runStop, currentLevel.messages.length || traces.length, nodeLabel) }}
            </p>
            <p
              v-else-if="!waveScore.won"
              class="text-xs text-muted"
            >
              {{ waveOutcomeSummary(waveScore) }}
            </p>
            <div
              v-if="newRecord"
              class="flex justify-center pt-2"
            >
              <UBadge
                label="New record!"
                icon="i-lucide-trophy"
                color="warning"
                variant="subtle"
                size="lg"
              />
            </div>
          </div>
          <UButton
            label="Show breakdown"
            icon="i-lucide-list"
            color="neutral"
            variant="outline"
            size="sm"
            @click="isBreakdownOpen = true"
          />
        </div>
        <UEmpty
          v-else
          icon="i-lucide-play"
          title="No runs yet"
          description="Run a wave to see which prompts got through and which were stopped."
          size="sm"
          variant="naked"
        />
      </div>
    </template>
    <template #footer>
      <div class="flex w-full flex-wrap items-center justify-between gap-2">
        <div class="ml-auto flex items-center gap-2">
          <UButton
            v-if="waveScore?.won && nextLevel"
            :to="canAccessLevel(nextLevel, session) === 'available' ? `/game?level=${nextLevel.id}` : '/plans'"
            label="Next Level"
            trailing-icon="i-lucide-arrow-right"
            color="neutral"
            variant="outline"
            size="md"
            @click="isResultsOpen = false"
          />
          <UButton
            label="Done"
            color="neutral"
            variant="solid"
            size="md"
            @click="isResultsOpen = false"
          />
        </div>
      </div>
    </template>
  </UModal>
  <!-- Mission Briefing Modal -->
  <CampaignLevelBriefingModal
    v-model:open="isBriefingOpen"
    :level="currentLevel"
    :stage-number="String(currentLevel.order).padStart(2, '0')"
    :stars="highStars"
    :best-score="highScore ?? 0"
    :won="Boolean(waveScore?.won)"
    :mastered="Boolean(waveScore?.follow_up_passed)"
    in-game
  />
  <!-- Score Breakdown Modal, opened from Run results (WEB-AGENT-021) -->
  <UModal
    v-model:open="isBreakdownOpen"
    title="Score breakdown"
    :ui="{ content: 'sm:max-w-2xl' }"
  >
    <template #body>
      <div
        v-if="waveScore"
        class="space-y-6"
      >
        <div
          :class="[
            'grid divide-x divide-default rounded-lg border border-default bg-elevated/30',
            breakdownStats(waveScore, currentLevelId).length === 3 ? 'grid-cols-3' : 'grid-cols-2'
          ]"
        >
          <div
            v-for="stat in breakdownStats(waveScore, currentLevelId)"
            :key="stat.label"
            class="min-w-0 px-4 py-3"
          >
            <p class="flex items-center gap-1.5 text-xs text-muted">
              <UIcon
                :name="stat.icon"
                class="size-3.5 shrink-0"
              />
              <span class="truncate">{{ stat.label }}</span>
            </p>
            <p class="mt-1 truncate text-lg font-semibold tabular-nums text-highlighted">
              {{ stat.value }}
            </p>
          </div>
        </div>
        <UAccordion
          :items="breakdownAccordionItems"
        >
          <template #body>
            <dl class="divide-y divide-default text-sm">
              <div
                v-for="row in scoreBreakdown(waveScore, currentLevelId)"
                :key="row.label"
                class="flex items-center justify-between py-2 tabular-nums"
              >
                <dt class="text-muted">
                  {{ row.label }}
                </dt>
                <dd :class="['font-medium', row.points < 0 ? 'text-error' : row.points > 0 ? 'text-highlighted' : 'text-dimmed']">
                  {{ (row.points || 0).toLocaleString() }}
                </dd>
              </div>
              <div class="flex items-center justify-between pt-3 tabular-nums">
                <dt class="font-semibold text-highlighted">
                  Total
                </dt>
                <dd class="text-base font-bold text-highlighted">
                  {{ waveScore.total_score.toLocaleString() }}
                </dd>
              </div>
            </dl>
          </template>
        </UAccordion>
        <div
          v-if="traces.length > 0"
          class="space-y-3"
        >
          <div class="flex items-center gap-1">
            <h3 class="text-sm font-semibold text-highlighted">
              Prompt outcomes
            </h3>
            <UTooltip text="Click a cell to see the prompts">
              <UButton
                icon="i-lucide-circle-question-mark"
                size="sm"
                variant="link"
              />
            </UTooltip>
          </div>
          <div class="grid grid-cols-[auto_1fr_1fr] gap-x-3 gap-y-2">
            <span />
            <span class="text-center text-xs font-medium text-muted">Got through</span>
            <span class="text-center text-xs font-medium text-muted">Stopped</span>
            <template
              v-for="cell in resultCells"
              :key="cell.key"
            >
              <span
                v-if="cell.rowLabel"
                class="self-center pe-1 text-right text-xs font-medium text-muted"
              >
                {{ cell.rowLabel }}
              </span>
              <UButton
                color="neutral"
                variant="ghost"
                :class="[
                  'group w-full flex-col items-center gap-1 rounded-xl py-5',
                  cell.items.length === 0
                    ? 'bg-elevated/30 hover:bg-elevated/60'
                    : cell.correct
                      ? 'bg-success/10 hover:bg-success/15'
                      : 'bg-error/10 hover:bg-error/15'
                ]"
                :aria-label="`${cell.title}: ${cell.items.length}. Show prompts`"
                @click="openResultCell(cell.key)"
              >
                <span :class="['text-3xl font-semibold tabular-nums', cell.items.length === 0 ? 'text-dimmed' : cell.correct ? 'text-success' : 'text-error']">
                  {{ cell.items.length }}
                </span>
                <span class="flex items-center gap-1.5 text-xs font-normal text-muted">
                  {{ cell.caption }}
                </span>
              </UButton>
            </template>
          </div>
        </div>
      </div>
    </template>
  </UModal>
  <!-- Matrix Cell Modal: the prompts in one confusion-matrix cell -->
  <UModal
    v-model:open="isResultCellOpen"
    :title="selectedResultCell.title"
    :ui="{
      content: 'sm:max-w-2xl',
      body: '[scrollbar-gutter:stable] [scrollbar-width:thin] [scrollbar-color:var(--ui-border-accented)_transparent]'
    }"
  >
    <template #body>
      <ul
        v-if="selectedResultCell.items.length > 0"
        class="space-y-2 text-sm"
      >
        <li
          v-for="group in promptGroups(selectedResultCell.items, traces, nodeLabel)"
          :key="group.family"
          class="rounded-md border border-default px-4 py-3"
        >
          <p class="font-medium text-highlighted">
            {{ group.family }}
          </p>
          <ul class="mt-1 space-y-0.5">
            <li
              v-for="row in group.rows"
              :key="row.key"
              class="text-muted"
            >
              {{ row.title }}<span v-if="row.detail">: {{ row.detail }}</span>
            </li>
          </ul>
        </li>
      </ul>
    </template>
  </UModal>
</template>
