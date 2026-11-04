<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import NodeContainer from './NodeContainer.vue'

defineProps<{
  data: {
    label?: string
    status?: string
  }
}>()
</script>

<template>
  <NodeContainer :status="data?.status">
    <Handle
      type="source"
      :position="Position.Right"
      class="w-2.5 h-2.5 bg-elevated border border-default"
    />
    <UIcon
      name="i-lucide-message-square"
      class="size-5 mb-1.5 text-highlighted"
    />
    <div class="text-xs font-semibold text-highlighted">
      Message
    </div>
    <div class="text-[11px] text-muted mt-1 max-w-36 truncate">
      {{ data?.label || 'Ready' }}
    </div>
  </NodeContainer>
</template>
