<script setup lang="ts">
defineProps<{
  alt: string
}>()

// The promo video is an animated WebP on the repository's `media` branch, served by GitHub
// rather than by Vercel, so the site deploy stays small.
const { t } = useI18n()
const runtimeConfig = useRuntimeConfig()
const src = computed(() => String(runtimeConfig.public.promoVideoUrl))
const STATIC_PREVIEW = '/images/board.webp'

const paused = ref(false)

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    paused.value = true
  }
})
</script>

<template>
  <div class="relative">
    <UPageCard
      variant="subtle"
      class="rounded-2xl"
    >
      <div class="relative">
        <picture>
          <source
            v-if="!paused"
            :srcset="STATIC_PREVIEW"
            media="(prefers-reduced-motion: reduce)"
          >
          <img
            :src="paused ? STATIC_PREVIEW : src"
            :alt="alt"
            width="1440"
            height="810"
            fetchpriority="high"
            class="rounded-xl aspect-video w-full bg-muted"
          >
        </picture>

        <UButton
          size="xs"
          color="neutral"
          variant="solid"
          :icon="paused ? 'i-lucide-play' : 'i-lucide-pause'"
          :aria-pressed="paused"
          :aria-label="paused ? t('nav.playAnimation') : t('nav.pauseAnimation')"
          class="absolute bottom-3 right-3 shadow-sm"
          @click="paused = !paused"
        />
      </div>
    </UPageCard>
  </div>
</template>
