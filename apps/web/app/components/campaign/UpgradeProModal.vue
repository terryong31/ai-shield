<script setup lang="ts">
const open = defineModel<boolean>('open', { default: false })

withDefaults(
  defineProps<{
    targetTitle?: string
  }>(),
  {
    targetTitle: 'Pro Campaign Level'
  }
)
</script>

<template>
  <UModal
    v-model:open="open"
    title="Upgrade to Pro"
    :ui="{ content: 'sm:max-w-md' }"
  >
    <template #body>
      <div class="space-y-4 text-sm text-default">
        <p class="leading-relaxed">
          <span class="font-semibold text-highlighted">{{ targetTitle }}</span> is part of the Pro campaign. Upgrade to unlock all 23 campaign levels, Hard constraint challenges, and the Custom Sandbox.
        </p>

        <div class="space-y-2.5 rounded-lg border border-default bg-elevated/40 p-4">
          <div class="flex items-center gap-2.5">
            <UIcon
              name="i-lucide-check"
              class="size-4 shrink-0 text-highlighted"
            />
            <span>All 18 Pro levels across Easy, Medium, and Hard</span>
          </div>
          <div class="flex items-center gap-2.5">
            <UIcon
              name="i-lucide-check"
              class="size-4 shrink-0 text-highlighted"
            />
            <span>300 wave runs and 1,000 live tests per day</span>
          </div>
          <div class="flex items-center gap-2.5">
            <UIcon
              name="i-lucide-check"
              class="size-4 shrink-0 text-highlighted"
            />
            <span>Custom Sandbox with your own agent and dataset</span>
          </div>
        </div>
      </div>
    </template>

    <template #footer>
      <div class="flex w-full items-center justify-end gap-2">
        <UButton
          label="Maybe Later"
          color="neutral"
          variant="link"
          size="md"
          @click="open = false"
        />
        <UButton
          to="/plans"
          label="View Plans"
          trailing-icon="i-lucide-arrow-right"
          color="neutral"
          variant="solid"
          size="md"
        />
      </div>
    </template>
  </UModal>
</template>
