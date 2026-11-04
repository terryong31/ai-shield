<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import NodeContainer from './NodeContainer.vue'

defineProps<{
  data: {
    status?: string
    reason?: string
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
    <UIcon
      name="i-lucide-shield-x"
      class="size-5 mb-1.5"
    />
    <div class="text-xs font-semibold">
      Blocked
    </div>
    <div
      v-if="data?.reason"
      class="text-[11px] opacity-80 mt-1 max-w-36 truncate"
    >
      {{ data.reason }}
    </div>
  </NodeContainer>
</template>
