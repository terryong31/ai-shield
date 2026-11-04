<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { NODE_CATALOG, type GameNodeData } from '~/utils/gameBoard'
import { statusAppearance } from '~/utils/pipelineGraph'

const props = defineProps<{
  id: string
  data: GameNodeData
  selected?: boolean
}>()

const meta = computed(() => NODE_CATALOG[props.data.kind])
const appearance = computed(() => statusAppearance(props.data.status))

const handleTopPercent = (index: number, total: number): string => {
  if (total <= 1) return '50%'
  if (total === 2) return index === 0 ? '35%' : '72%'
  return index === 0 ? '28%' : index === 1 ? '54%' : '80%'
}

const handleLabel = (handle: string): string => {
  if (handle === 'suspicious') return 'unclear'
  return handle
}
</script>

<template>
  <div
    class="w-48 rounded border transition-colors duration-150 select-none"
    :class="[
      appearance.class,
      selected ? 'ring-2 ring-inverted' : '',
      data.status === 'blocked' ? 'bg-inverted text-inverted border-inverted' : 'bg-default text-default'
    ]"
  >
    <Handle
      v-if="data.hasInput"
      type="target"
      :position="Position.Left"
      :connectable="true"
      class="w-3.5 h-3.5 bg-elevated border border-accented"
    />

    <!-- Header -->
    <div
      class="flex items-center justify-between gap-1.5 px-3 py-2.5 border-b"
      :class="data.status === 'blocked' ? 'border-inverted/20' : 'border-default bg-elevated/60'"
    >
      <div class="flex items-center gap-1.5 min-w-0">
        <UIcon
          :name="meta.icon"
          class="size-4 shrink-0"
        />
        <span class="text-sm font-semibold tracking-tight truncate">
          {{ data.label }}
        </span>
      </div>

      <UBadge
        v-if="data.isAnchor"
        label="LOCKED"
        color="neutral"
        variant="outline"
        size="sm"
        class="text-xs uppercase shrink-0"
      />
    </div>

    <!-- Body -->
    <div class="px-3 py-2.5 space-y-2">
      <!-- Live counters for Safe/Assistant and Blocked nodes -->
      <div
        v-if="data.kind === 'assistant'"
        class="grid grid-cols-2 gap-1.5 text-xs tabular-nums"
      >
        <div class="rounded border border-default/60 px-2 py-1">
          <div class="text-[11px] uppercase opacity-70">
            In
          </div>
          <div class="text-sm font-bold">
            {{ data.arrivedCount }}
          </div>
        </div>
        <div class="rounded border border-default/60 px-2 py-1">
          <div class="text-[11px] uppercase opacity-70">
            Leaked
          </div>
          <div class="text-sm font-bold">
            {{ data.flaggedCount }}
          </div>
        </div>
      </div>

      <div
        v-else-if="data.kind === 'blocked'"
        class="grid grid-cols-2 gap-1.5 text-xs tabular-nums"
      >
        <div class="rounded border border-default/60 px-2 py-1">
          <div class="text-[11px] uppercase opacity-70">
            Blocked
          </div>
          <div class="text-sm font-bold">
            {{ data.arrivedCount }}
          </div>
        </div>
        <div class="rounded border border-default/60 px-2 py-1">
          <div class="text-[11px] uppercase opacity-70">
            False
          </div>
          <div class="text-sm font-bold">
            {{ data.flaggedCount }}
          </div>
        </div>
      </div>

      <div
        v-else-if="data.kind === 'incoming'"
        class="flex items-center justify-between text-xs tabular-nums"
      >
        <span class="opacity-75">Sent</span>
        <span class="text-sm font-bold">{{ data.arrivedCount }}</span>
      </div>

      <!-- Tool node metrics -->
      <div
        v-else
        class="flex items-center justify-between text-xs tabular-nums"
        :class="data.status === 'blocked' ? 'opacity-90' : 'text-dimmed'"
      >
        <span>{{ data.latencyMs.toFixed(1) }}ms</span>
        <span>${{ data.costUsd.toFixed(4) }}</span>
        <span>{{ data.hits }}x</span>
      </div>

      <div
        v-if="data.handles.length > 0"
        class="pt-1 flex flex-col items-end gap-1"
      >
        <div
          v-for="(handle, idx) in data.handles"
          :key="handle"
          class="flex items-center gap-1 text-xs uppercase tracking-wider"
          :class="data.status === 'blocked' ? 'opacity-90' : 'text-dimmed'"
        >
          <span>{{ handleLabel(handle) }}</span>
          <Handle
            :id="handle"
            type="source"
            :position="Position.Right"
            :connectable="true"
            :style="{ top: handleTopPercent(idx, data.handles.length) }"
            class="w-3.5 h-3.5 bg-elevated border border-accented"
          />
        </div>
      </div>
    </div>
  </div>
</template>
