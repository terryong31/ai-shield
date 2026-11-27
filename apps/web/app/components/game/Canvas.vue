<!-- The Vue Flow board where checks are placed and wired (spec 0055). State comes from useGamePage. -->
<script setup lang="ts">
import { Background } from '@vue-flow/background'
import { VueFlow } from '@vue-flow/core'
import GameNode from '~/components/workflow/GameNode.vue'

const {
  FLOW_ID,
  currentLevel,
  edges,
  isLoadingBoard,
  isProLevelLocked,
  nodes,
  onCanvasDragOver,
  onCanvasDrop,
  onConnect,
  onEdgesChange,
  onNodeClick,
  onNodeDoubleClick,
  onNodesChange
} = useGameContext()
</script>

<template>
  <!-- Center Canvas -->
  <main
    class="relative isolate flex-1 h-full min-w-0 bg-default"
    data-tour="canvas"
    @dragover="onCanvasDragOver"
    @drop="onCanvasDrop"
  >
    <VueFlow
      :id="FLOW_ID"
      v-model:nodes="nodes"
      v-model:edges="edges"
      :default-zoom="0.95"
      :min-zoom="0.35"
      :max-zoom="1.75"
      fit-view-on-init
      class="h-full w-full"
      @nodes-change="onNodesChange"
      @edges-change="onEdgesChange"
      @node-click="onNodeClick"
      @node-double-click="onNodeDoubleClick"
      @connect="onConnect"
    >
      <template #node-gameNode="nodeProps">
        <GameNode v-bind="nodeProps" />
      </template>
      <Background
        :gap="20"
        :size="1"
        color="var(--ui-border-accented)"
      />
    </VueFlow>
    <div
      v-if="isProLevelLocked"
      class="absolute inset-0 z-30 flex items-center justify-center bg-default/85 p-6 backdrop-blur-sm"
    >
      <UCard
        variant="outline"
        :ui="{ root: 'w-full max-w-md', body: 'space-y-4 p-6 text-center' }"
      >
        <div class="mx-auto flex size-12 items-center justify-center rounded-full border border-default bg-elevated text-highlighted">
          <UIcon
            name="i-lucide-lock"
            class="size-5"
          />
        </div>
        <div class="space-y-1">
          <h2 class="text-lg font-bold text-highlighted">
            Pro Level Locked
          </h2>
          <p class="text-sm text-muted">
            {{ currentLevel.title }} is part of the Pro campaign. Upgrade your plan to play all 23 campaign levels.
          </p>
        </div>
        <div class="flex flex-wrap items-center justify-center gap-2 pt-2">
          <UButton
            to="/plans"
            label="Upgrade to Pro"
            icon="i-lucide-sparkles"
            color="neutral"
            variant="solid"
            size="md"
          />
        </div>
      </UCard>
    </div>
    <div
      v-else-if="isLoadingBoard"
      class="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 bg-default/80 backdrop-blur-sm"
    >
      <UIcon
        name="i-lucide-loader-circle"
        class="size-6 animate-spin text-highlighted"
      />
      <p class="text-sm font-medium text-muted">
        Loading workflow...
      </p>
    </div>
  </main>
</template>
