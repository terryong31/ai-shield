<script setup lang="ts">
import { computed } from 'vue'
import { statusAppearance, type NodeStatus } from '~/utils/pipelineGraph'

const props = defineProps<{
  status?: string
  className?: string
}>()

const normalizedStatus = computed<NodeStatus>(() => {
  switch (props.status) {
    case 'active':
      return 'active'
    case 'success':
    case 'passed':
      return 'passed'
    case 'warning':
    case 'flagged':
      return 'flagged'
    case 'error':
    case 'blocked':
      return 'blocked'
    case 'skipped':
      return 'skipped'
    default:
      return 'idle'
  }
})

const appearance = computed(() => statusAppearance(normalizedStatus.value))
</script>

<template>
  <div
    class="flex flex-col items-center justify-center p-3 rounded border transition-colors duration-150 min-w-36 bg-default"
    :class="[appearance.class, className]"
  >
    <slot />
  </div>
</template>
