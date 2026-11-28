<script setup lang="ts">
defineProps<{
  src: string
  alt: string
}>()
</script>

<template>
  <UPageCard variant="subtle">
    <img
      :src="src"
      :alt="alt"
      width="1396"
      height="868"
      loading="lazy"
      class="rounded-sm border border-default w-full h-auto"
    >
  </UPageCard>
</template>
