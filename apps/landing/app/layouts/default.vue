<script setup lang="ts">
const { t } = useI18n()
</script>

<template>
  <div>
    <a
      href="#main-content"
      class="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-default focus:px-3 focus:py-2 focus:text-highlighted focus:ring-2 focus:ring-primary"
    >
      {{ t('nav.skipToContent') }}
    </a>

    <AppHeader />

    <UMain
      id="main-content"
      tabindex="-1"
      class="focus:outline-none"
    >
      <slot />
    </UMain>

    <AppFooter />
  </div>
</template>
