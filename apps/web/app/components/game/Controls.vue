<!-- Run, Restart, Save, Guide and Hint, and the custom test bar of the game page (spec 0055). State comes from useGamePage. -->
<script setup lang="ts">
import { canRunCustom } from '~/utils/customSandbox'
import { attemptsLeftLabel, runsRemaining } from '~/utils/gameBoard'

const {
  customAgent,
  customApiKey,
  customDataset,
  customMessage,
  handleRestart,
  handleRunWave,
  handleSaveBoard,
  handleTestCustomMessage,
  hasLevelHint,
  hasLevelTour,
  hasUnsavedChanges,
  isAnonymous,
  isCustomMode,
  isHintOpen,
  maxCheckNodes,
  openSignInPrompt,
  placedCheckNodeCount,
  runningWave,
  savingBoard,
  session,
  showAttempts,
  startLevelTour
} = useGameContext()
</script>

<template>
  <!-- Top Nav 2: Replaces bottom nav (Wave controls + Custom test bar) -->
  <div class="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-default bg-elevated/30 px-4">
    <div class="flex items-center gap-2">
      <UButton
        label="Run wave"
        data-tour="run-wave"
        icon="i-lucide-play"
        color="neutral"
        variant="solid"
        size="lg"
        :loading="runningWave"
        :disabled="isCustomMode && !canRunCustom(customAgent, customDataset, customApiKey) || (showAttempts && runsRemaining(session, 'wave') === 0)"
        @click="handleRunWave()"
      />
      <UButton
        label="Restart"
        icon="i-lucide-rotate-ccw"
        color="neutral"
        variant="ghost"
        size="lg"
        @click="handleRestart"
      />
      <UChip
        :show="hasUnsavedChanges"
        color="primary"
        size="md"
      >
        <UButton
          label="Save"
          icon="i-lucide-save"
          color="neutral"
          variant="ghost"
          size="lg"
          :loading="savingBoard"
          :aria-label="hasUnsavedChanges ? 'Save (unsaved changes)' : 'Save'"
          @click="isAnonymous ? openSignInPrompt('save') : handleSaveBoard()"
        />
      </UChip>
      <UButton
        v-if="hasLevelTour"
        label="Guide"
        icon="i-lucide-map"
        color="neutral"
        variant="ghost"
        size="lg"
        @click="startLevelTour"
      />
      <UButton
        v-if="hasLevelHint"
        label="Hint"
        icon="i-lucide-lightbulb"
        color="neutral"
        variant="ghost"
        size="lg"
        @click="isHintOpen = true"
      />
      <template v-if="showAttempts">
        <USeparator
          orientation="vertical"
          class="h-5 px-1"
        />
        <span class="text-sm tabular-nums text-muted">
          {{ attemptsLeftLabel(session) }}
        </span>
      </template>
      <template v-if="maxCheckNodes !== null">
        <USeparator
          orientation="vertical"
          class="h-5 px-1"
        />
        <span class="text-sm tabular-nums text-muted">
          {{ placedCheckNodeCount }} / {{ maxCheckNodes }} nodes
        </span>
      </template>
    </div>
    <div
      v-if="isCustomMode"
      class="flex items-center gap-2 w-full max-w-md"
      data-tour="test-bar"
    >
      <UInput
        v-model="customMessage"
        placeholder="Test a message..."
        size="lg"
        class="flex-1"
        @keydown.enter="handleTestCustomMessage()"
      />
      <UButton
        label="Test"
        icon="i-lucide-send"
        color="neutral"
        variant="solid"
        size="lg"
        :loading="runningWave"
        @click="handleTestCustomMessage()"
      />
    </div>
  </div>
</template>
