<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import NodeContainer from './NodeContainer.vue'

defineProps<{
  data: {
    status?: string
    tools?: string[]
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
      name="i-lucide-wrench"
      class="size-5 mb-1.5 text-highlighted"
    />
    <div class="text-xs font-semibold text-highlighted">
      Tools used
    </div>
    <div
      v-if="data?.tools?.length"
      class="mt-1 flex flex-wrap gap-1 justify-center max-w-40"
    >
      <UBadge
        v-for="tool in data.tools"
        :key="tool"
        :label="tool"
        color="neutral"
        variant="outline"
        size="xs"
      />
    </div>
  </NodeContainer>
</template>
