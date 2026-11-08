<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { NODE_CATALOG, type GameNodeData } from '~/utils/gameBoard'

const props = defineProps<{
  id: string
  data: GameNodeData
  selected?: boolean
}>()

const meta = computed(() => NODE_CATALOG[props.data.kind])
const hasRun = computed(() => props.data.traffic.in > 0)

const summary = computed(() => {
  if (props.data.kind === 'incoming') return 'Prompts enter the board here'
  if (props.data.kind === 'assistant') return 'Answers the prompts that reach it'
  return props.data.subtitle
})

// Vue Flow joins a wire to the outer edge of a handle's box (left edge for an input,
// right edge for an output). A zero-size handle puts that point at the dot's centre on
// both sides, and the dot itself is drawn as a child sitting over the node border.
const HANDLE_ANCHOR = {
  width: '0px',
  height: '0px',
  minWidth: '0px',
  minHeight: '0px',
  border: 'none',
  background: 'transparent',
  transform: 'none'
}
const IN_PORT_STYLE = { ...HANDLE_ANCHOR, left: '-1px' }
const OUT_PORT_STYLE = { ...HANDLE_ANCHOR, right: '-1px', left: 'auto' }

const handleLabel = (handle: string): string => {
  if (handle === 'suspicious') return 'unclear'
  if (handle === 'safe') return 'pass'
  return handle
}
</script>

<template>
  <div
    class="w-56 rounded-md border-2 bg-default text-default transition-colors duration-150 select-none"
    :class="selected
      ? 'border-solid border-inverted'
      : data.isAnchor ? 'border-dashed border-accented' : 'border-solid border-default'"
  >
    <!-- Header: type icon and name -->
    <div class="flex min-w-0 items-center gap-1.5 border-b border-default bg-elevated/60 px-3 py-2">
      <UIcon
        :name="meta.icon"
        class="size-4 shrink-0"
      />
      <span class="truncate text-sm font-semibold tracking-tight">
        {{ data.label }}
      </span>
    </div>

    <!-- Body -->
    <p class="truncate px-3 pt-2 text-xs text-muted">
      {{ summary }}
    </p>

    <!-- Ports below the description: input on the left, outputs on the right -->
    <div
      v-if="data.hasInput || data.handles.length > 0"
      class="flex items-start justify-between gap-2 py-2"
    >
      <div
        v-if="data.hasInput"
        class="relative px-3 text-xs uppercase tracking-wider text-dimmed"
      >
        in
        <Handle
          type="target"
          :position="Position.Left"
          :connectable="true"
          :style="IN_PORT_STYLE"
        >
          <span class="pointer-events-auto absolute top-0 left-0 size-2 -translate-1/2 rounded-full border-2 border-inverted bg-default" />
        </Handle>
      </div>
      <span v-else />

      <!-- Output ports, labelled even when wired -->
      <div
        v-if="data.handles.length > 0"
        class="space-y-1"
      >
        <div
          v-for="handle in data.handles"
          :key="handle"
          class="relative flex items-center justify-end gap-2 px-3 text-xs uppercase tracking-wider text-dimmed"
        >
          <span>{{ handleLabel(handle) }}</span>
          <Handle
            :id="handle"
            type="source"
            :position="Position.Right"
            :connectable="true"
            :style="OUT_PORT_STYLE"
          >
            <span class="pointer-events-auto absolute top-0 left-0 size-2 -translate-1/2 rounded-full border-2 border-inverted bg-default" />
          </Handle>
        </div>
      </div>
    </div>

    <!-- Live counts after a run -->
    <div
      v-if="hasRun"
      class="grid grid-cols-3 gap-1 border-t border-default px-3 py-2 text-xs tabular-nums"
    >
      <template v-if="data.kind === 'assistant'">
        <span><span class="text-dimmed">in</span> {{ data.arrivedCount }}</span>
        <span><span class="text-dimmed">leaked</span> {{ data.flaggedCount }}</span>
        <span><span class="text-dimmed">tok</span> {{ data.tokens.toLocaleString() }}</span>
      </template>
      <template v-else>
        <span><span class="text-dimmed">in</span> {{ data.traffic.in }}</span>
        <span><span class="text-dimmed">pass</span> {{ data.traffic.pass }}</span>
        <span><span class="text-dimmed">block</span> {{ data.traffic.block }}</span>
      </template>
    </div>
  </div>
</template>
