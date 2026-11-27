<!-- Small dialogs of the game page: tool info, sign-in, draft choice, quit and hint (spec 0055). State comes from useGamePage. -->
<script setup lang="ts">
import { formatCheckCost } from '~/utils/gameBoard'

const {
  confirmQuitToMenu,
  currentLevel,
  hasLevelHint,
  infoTool,
  isDraftConflictOpen,
  isHintOpen,
  isQuitModalOpen,
  isSignInPromptOpen,
  isToolInfoOpen,
  keepLocalBoard,
  useSavedBoard
} = useGameContext()
</script>

<template>
  <!-- Tool Info Modal -->
  <UModal
    v-model:open="isToolInfoOpen"
    :title="infoTool?.label ?? 'Tool details'"
  >
    <template #body>
      <div
        v-if="infoTool"
        class="space-y-4 text-sm"
      >
        <p class="text-default">
          {{ infoTool.summary }}
        </p>
        <dl class="space-y-3 border-t border-default pt-4">
          <div class="flex items-center justify-between gap-4">
            <dt class="text-muted">
              Latency
            </dt>
            <dd class="font-medium tabular-nums text-highlighted">
              {{ infoTool.latency_ms }} ms
            </dd>
          </div>
          <div class="flex items-center justify-between gap-4">
            <dt class="text-muted">
              Cost per message
            </dt>
            <dd class="font-medium tabular-nums text-highlighted">
              {{ formatCheckCost(infoTool.cost_usd) }}
            </dd>
          </div>
        </dl>
      </div>
    </template>
  </UModal>
  <!-- Sign-in prompt shown to anonymous players who try to save -->
  <UModal
    v-model:open="isSignInPromptOpen"
    title="Sign in to save your board"
  >
    <template #body>
      <p class="text-sm text-default">
        Sign in to save your board. Saved boards come back when you open the level again, on any device.
      </p>
    </template>
    <template #footer>
      <div class="flex w-full items-center justify-end gap-2">
        <UButton
          to="/auth/login"
          label="Sign in"
          color="neutral"
          variant="solid"
          size="md"
        />
      </div>
    </template>
  </UModal>
  <!-- Local Draft Conflict Modal (WEB-DRAFT-005) -->
  <UModal
    v-model:open="isDraftConflictOpen"
    title="Which board do you want to keep?"
    description="This browser has a board from before you signed in, and your account has a saved board for this level."
    :dismissible="false"
  >
    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          label="Use saved board"
          color="neutral"
          variant="ghost"
          @click="useSavedBoard"
        />
        <UButton
          label="Keep local board"
          color="neutral"
          variant="solid"
          @click="keepLocalBoard"
        />
      </div>
    </template>
  </UModal>
  <!-- Quit Confirmation Modal -->
  <UModal
    v-model:open="isQuitModalOpen"
    title="Quit Game"
  >
    <template #body>
      <p class="text-base text-default">
        Are you sure you want to quit? Your progress will not be saved
      </p>
    </template>
    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          label="Cancel"
          color="neutral"
          variant="ghost"
          size="md"
          @click="isQuitModalOpen = false"
        />
        <UButton
          label="Quit"
          color="error"
          variant="solid"
          size="md"
          @click="confirmQuitToMenu"
        />
      </div>
    </template>
  </UModal>

  <CampaignLevelHintModal
    v-if="hasLevelHint"
    v-model:open="isHintOpen"
    :level="currentLevel"
  />
</template>
