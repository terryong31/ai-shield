<script setup lang="ts">
import type { GameLevelSchema } from '~/types/api'
import { starCriteria } from '~/utils/campaignSelect'

const open = defineModel<boolean>('open', { default: false })

withDefaults(
  defineProps<{
    level: GameLevelSchema | null
    stageNumber?: string
    stars?: number
    bestScore?: number
    won?: boolean
    mastered?: boolean
    inGame?: boolean
  }>(),
  {
    stageNumber: '01',
    stars: 0,
    bestScore: 0,
    won: false,
    mastered: false,
    inGame: false
  }
)
</script>

<template>
  <UModal
    v-model:open="open"
    :title="level?.title ?? 'Mission Briefing'"
    :ui="{ content: 'sm:max-w-md' }"
  >
    <template #body>
      <div
        v-if="level"
        class="space-y-5 text-sm"
      >
        <p class="leading-relaxed text-default">
          {{ level.new_idea }}
        </p>

        <section class="space-y-1">
          <h3 class="font-semibold text-highlighted">
            Objective
          </h3>
          <dl class="space-y-1">
            <div
              v-for="star in starCriteria(level)"
              :key="star.label"
              class="flex gap-2"
            >
              <dt class="shrink-0 text-muted">
                {{ star.label }}:
              </dt>
              <dd class="text-default">
                {{ star.goal }}
              </dd>
            </div>
          </dl>
        </section>

        <div class="space-y-4 flex flex-col items-center">
          <UInputRating
            :model-value="stars"
            :length="3"
            readonly
            color="warning"
            size="xl"
            :aria-label="`${stars} of 3 stars`"
          />
          <p class="text-sm text-muted">
            High score: <span class="font-semibold tabular-nums text-highlighted">{{ bestScore.toLocaleString() }}</span>
          </p>
        </div>
      </div>
    </template>

    <template #footer>
      <div
        v-if="level"
        class="ml-auto flex items-center justify-end gap-2"
      >
        <UButton
          v-if="inGame"
          label="Back to Board"
          color="neutral"
          variant="solid"
          size="md"
          @click="open = false"
        />
        <UButton
          v-else
          :to="`/game?level=${level.id}`"
          label="Play Level"
          icon="i-lucide-play"
          color="neutral"
          variant="solid"
          size="lg"
        />
      </div>
    </template>
  </UModal>
</template>
