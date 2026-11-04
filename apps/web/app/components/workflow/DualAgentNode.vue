<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import NodeContainer from './NodeContainer.vue'

defineProps<{
  data: {
    status?: string
    currentMessage?: string
  }
}>()
</script>

<template>
  <NodeContainer
    :status="data?.status"
    class-name="min-w-44"
  >
    <Handle
      type="target"
      :position="Position.Left"
      class="w-2.5 h-2.5 bg-elevated border border-default"
    />
    <Handle
      id="safe"
      type="source"
      :position="Position.Right"
      class="w-2.5 h-2.5 top-1/3 bg-elevated border border-default"
    />
    <Handle
      id="danger"
      type="source"
      :position="Position.Right"
      class="w-2.5 h-2.5 top-2/3 bg-elevated border border-default"
    />

    <UIcon
      name="i-lucide-scale"
      class="size-5 mb-1.5 text-highlighted"
    />
    <div class="text-xs font-semibold text-highlighted">
      Agent review
    </div>
    <div
      v-if="data?.currentMessage"
      class="text-[11px] text-muted mt-1 max-w-40 truncate"
    >
      {{ data.currentMessage }}
    </div>
  </NodeContainer>
</template>
