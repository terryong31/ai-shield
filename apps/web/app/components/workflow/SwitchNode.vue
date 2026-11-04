<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import NodeContainer from './NodeContainer.vue'

defineProps<{
  data: {
    status?: string
    verdict?: string
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
      id="safe"
      type="source"
      :position="Position.Right"
      class="w-2.5 h-2.5 top-1/4 bg-elevated border border-default"
    />
    <Handle
      id="uncertain"
      type="source"
      :position="Position.Right"
      class="w-2.5 h-2.5 top-1/2 bg-elevated border border-default"
    />
    <Handle
      id="danger"
      type="source"
      :position="Position.Right"
      class="w-2.5 h-2.5 top-3/4 bg-elevated border border-default"
    />

    <UIcon
      name="i-lucide-git-branch"
      class="size-5 mb-1.5 text-highlighted"
    />
    <div class="text-xs font-semibold text-highlighted">
      Decision
    </div>
    <UBadge
      v-if="data?.verdict"
      :label="data.verdict"
      color="neutral"
      variant="outline"
      size="xs"
      class="mt-1"
    />
  </NodeContainer>
</template>
