<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import NodeContainer from './NodeContainer.vue'

defineProps<{
  data: {
    status?: string
    policy?: string
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
      name="i-lucide-bot"
      class="size-5 mb-1.5 text-highlighted"
    />
    <div class="text-xs font-semibold text-highlighted">
      Assistant
    </div>
    <UBadge
      v-if="data?.policy"
      :label="data.policy"
      color="neutral"
      variant="outline"
      size="xs"
      class="mt-1"
    />
  </NodeContainer>
</template>
