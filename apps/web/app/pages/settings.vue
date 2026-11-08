<script setup lang="ts">
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="flex min-h-full w-full items-center justify-center gap-4 p-4">
      <div class="flex flex-col items-center gap-3">
        <div class="flex items-center justify-start gap-3 w-full">
          <UButton
            to="/"
            label="Back"
            icon="i-lucide-arrow-left"
            color="neutral"
            variant="link"
            size="xl"
            class="text-base"
          />
          <span class="text-base font-bold uppercase tracking-wider text-highlighted">
            Settings
          </span>
        </div>
        <UPageCard class="w-full max-w-md min-w-190">
          <div class="flex items-center justify-between gap-4">
            <span class="text-base font-medium text-highlighted">
              Theme
            </span>
            <UColorModeSelect size="lg" />
          </div>
        </UPageCard>
      </div>
    </div>
  </div>
</template>
