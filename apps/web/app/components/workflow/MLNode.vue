<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import NodeContainer from './NodeContainer.vue'

defineProps<{
  data: {
    status?: string
    confidence?: number | null
  }
}>()
</script>

<template>
  <NodeContainer :status="data?.status">
    <Handle
      type="target"
      :position="Position.Left"
      class="w-2.5 h-2.5 bg-elevated border border-default"
    />
    <Handle
      type="source"
      :position="Position.Right"
      class="w-2.5 h-2.5 bg-elevated border border-default"
    />
    <UIcon
      name="i-lucide-gauge"
      class="size-5 mb-1.5 text-highlighted"
    />
    <div class="text-xs font-semibold text-highlighted">
      Quick screen
    </div>
    <div
      v-if="data?.confidence !== null && data?.confidence !== undefined"
      class="text-[11px] text-muted mt-1 tabular-nums"
    >
      Risk: {{ (Number(data.confidence) * 100).toFixed(1) }}%
    </div>
  </NodeContainer>
</template>
