<script setup lang="ts">
import type { GameLevelSchema } from '~/types/api'
import { familyName } from '~/utils/gameBoard'

// A free hint (WEB-LADDER-003): examples of the attacks in the wave, one card a family.
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  level: GameLevelSchema
}>()

const groups = computed(() => {
  const byFamily = new Map<string, string[]>()
  for (const example of props.level.briefing ?? []) {
    const texts = byFamily.get(example.family) ?? []
    texts.push(example.text)
    byFamily.set(example.family, texts)
  }
  return [...byFamily].map(([family, texts]) => ({ family, texts }))
})
</script>

<template>
  <UModal
    v-model:open="open"
    title="Hint"
    description="Examples of the attacks in this wave."
    :ui="{ content: 'sm:max-w-md' }"
  >
    <template #body>
      <ul class="space-y-2 text-sm">
        <li
          v-for="group in groups"
          :key="group.family"
          class="rounded-md bg-elevated/40 px-3 py-2"
        >
          <p class="text-xs font-medium text-muted">
            {{ familyName(group.family) }}
          </p>
          <ul class="mt-1 space-y-1">
            <li
              v-for="text in group.texts"
              :key="text"
              class="break-words text-default"
            >
              {{ text }}
            </li>
          </ul>
        </li>
      </ul>
    </template>

    <template #footer>
      <UButton
        class="ml-auto"
        label="Back to Board"
        color="neutral"
        variant="solid"
        @click="open = false"
      />
    </template>
  </UModal>
</template>
