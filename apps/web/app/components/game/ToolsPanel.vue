<!-- The collapsible tools panel: drag or tap a check to place it (spec 0055). State comes from useGamePage. -->
<script setup lang="ts">
import { isCheckDisabledByConstraints } from '~/utils/campaignSelect'
import { NODE_CATALOG, canUseNodeKind, formatCheckCost, nodeKeyRequirement } from '~/utils/gameBoard'

const {
  checks,
  currentLevel,
  handlePlaceCheck,
  isSidebarCollapsed,
  isToolLocked,
  nodeKeyState,
  onToolDragStart,
  openToolInfo,
  session,
  toolCardUi
} = useGameContext()
</script>

<template>
  <!-- Left Panel: Tools -->
  <div
    class="relative z-10 flex shrink-0 h-full"
    :class="isSidebarCollapsed ? 'w-0' : 'w-88'"
  >
    <aside
      v-show="!isSidebarCollapsed"
      class="flex h-full w-full cursor-default flex-col border-r border-default bg-elevated/20 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      <div class="border-b border-default px-3 py-3">
        <h2 class="text-sm font-bold uppercase tracking-wider text-highlighted">
          Tools
        </h2>
      </div>
      <div class="grid grid-cols-2 gap-2 p-2.5">
        <UCard
          v-for="chk in checks"
          :key="chk.kind"
          role="button"
          tabindex="0"
          :aria-label="`Add ${chk.label}`"
          :data-tour="`tool-${chk.kind}`"
          :aria-disabled="isToolLocked(chk.kind)"
          :ui="toolCardUi"
          :class="isToolLocked(chk.kind) ? 'cursor-not-allowed opacity-50 hover:opacity-100 focus-visible:opacity-100' : 'cursor-pointer'"
          :draggable="!isToolLocked(chk.kind)"
          @click="handlePlaceCheck(chk.kind)"
          @keydown.enter.self="handlePlaceCheck(chk.kind)"
          @keydown.space.self.prevent="handlePlaceCheck(chk.kind)"
          @dragstart="onToolDragStart($event, chk.kind)"
        >
          <template #header>
            <div class="flex items-center justify-between gap-1">
              <span class="min-w-0 truncate text-xs font-bold text-highlighted">
                {{ chk.label }}
              </span>
              <UButton
                icon="i-lucide-info"
                color="neutral"
                variant="ghost"
                size="xs"
                square
                :aria-label="`About ${chk.label}`"
                class="relative z-20 -my-1 shrink-0"
                @click.stop="openToolInfo(chk)"
              />
            </div>
          </template>
          <div class="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-default/60 p-3 text-center text-xs font-medium text-highlighted opacity-0 backdrop-blur-sm transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
            {{ isCheckDisabledByConstraints(chk.kind, currentLevel.constraints) ? 'Disabled in this level' : !canUseNodeKind(chk.kind, session) ? 'Sign in to unlock' : (nodeKeyRequirement(chk.kind, nodeKeyState) || 'Click or drag into canvas') }}
          </div>
          <UIcon
            :name="NODE_CATALOG[chk.kind]?.icon || 'i-lucide-box'"
            class="size-7 shrink-0 text-muted"
          />
          <p class="line-clamp-2 text-xs leading-tight text-muted">
            {{ NODE_CATALOG[chk.kind]?.subtitle }}
          </p>
          <template #footer>
            <div
              v-if="!isToolLocked(chk.kind)"
              class="flex items-center justify-between gap-1 text-xs tabular-nums text-dimmed"
            >
              <span>{{ chk.latency_ms.toFixed(0) }}ms</span>
              <span>{{ formatCheckCost(chk.cost_usd) }}</span>
            </div>
            <div
              v-else-if="isCheckDisabledByConstraints(chk.kind, currentLevel.constraints)"
              class="flex items-center justify-center gap-1 text-xs text-dimmed"
            >
              <UIcon
                name="i-lucide-ban"
                class="size-3 shrink-0"
              />
              <span>Disabled</span>
            </div>
            <div
              v-else
              class="flex items-center justify-center gap-1 text-xs text-dimmed"
            >
              <UIcon
                name="i-lucide-lock"
                class="size-3 shrink-0"
              />
              <span>{{ !canUseNodeKind(chk.kind, session) ? 'Sign in' : 'API key' }}</span>
            </div>
          </template>
        </UCard>
      </div>
    </aside>
    <!-- Middle-right collapsible close / expand button -->
    <UButton
      :icon="isSidebarCollapsed ? 'i-lucide-chevron-right' : 'i-lucide-chevron-left'"
      color="neutral"
      variant="outline"
      size="lg"
      square
      :aria-label="isSidebarCollapsed ? 'Open tools sidebar' : 'Close tools sidebar'"
      :class="[
        'absolute top-1/2 z-40 -translate-y-1/2 bg-default',
        isSidebarCollapsed ? 'left-2' : 'right-0 translate-x-1/2'
      ]"
      @click="isSidebarCollapsed = !isSidebarCollapsed"
    />
  </div>
</template>
