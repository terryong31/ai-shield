<script setup lang="ts">
const { loadPassphrase } = usePassphrase()

onMounted(loadPassphrase)
</script>

<template>
  <UApp>
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </UApp>
</template>
