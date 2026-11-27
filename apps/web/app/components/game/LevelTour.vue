<!-- The guided tour of the introductory levels (spec 0055). State comes from useGamePage. -->
<script setup lang="ts">
const {
  endLevelTour,
  isLastTourStep,
  nextTourStep,
  tour
} = useGameContext()
</script>

<template>
  <!-- Guided tour for introductory levels (WEB-CAMP-007) -->
  <UPopover
    :open="tour.open.value"
    :reference="tour.reference.value"
    :dismissible="false"
    :content="{ side: tour.current.value?.side ?? 'bottom', sideOffset: 12, collisionPadding: 16 }"
    arrow
  >
    <template #content>
      <div
        v-if="tour.current.value"
        class="w-80 space-y-3 p-4"
      >
        <div class="flex items-center justify-between gap-2">
          <p class="text-sm font-semibold text-highlighted">
            {{ tour.current.value.title }}
          </p>
          <span class="shrink-0 text-xs tabular-nums text-dimmed">
            {{ tour.index.value + 1 }} / {{ tour.total.value }}
          </span>
        </div>
        <p class="text-sm text-muted">
          {{ tour.current.value.body }}
        </p>
        <div class="flex items-center justify-between gap-2">
          <UButton
            label="Skip"
            color="neutral"
            variant="link"
            size="sm"
            @click="endLevelTour"
          />
          <div class="flex items-center gap-2">
            <UButton
              v-if="tour.hasPrev.value"
              label="Back"
              color="neutral"
              variant="outline"
              size="sm"
              @click="tour.prev()"
            />
            <UButton
              :label="isLastTourStep ? 'Finish' : 'Next'"
              color="neutral"
              variant="solid"
              size="sm"
              @click="nextTourStep"
            />
          </div>
        </div>
      </div>
    </template>
  </UPopover>
</template>
