<script setup lang="ts">
import {
  DEFAULT_DESCRIPTION,
  SITE_NAME,
  TWITTER_CARD_ALT,
  TWITTER_CARD_PATH,
  buildGameJsonLd,
  resolveSiteUrl
} from '~/utils/seo'

import { isValidLevelId } from '~/utils/gameBoard'

const { loadAccess } = useAdminAccess()
const route = useRoute()
const runtimeConfig = useRuntimeConfig()
const siteUrl = computed(() => resolveSiteUrl(runtimeConfig.public.siteUrl))
const INDEXABLE_PATHS = new Set(['/', '/game', '/plans', '/auth/login', '/auth/register'])
const canonicalUrl = computed(() => {
  if (!INDEXABLE_PATHS.has(route.path)) return null
  if (route.path === '/game') {
    const level = route.query.level
    if (isValidLevelId(level)) {
      return `${siteUrl.value}/game?level=${level}`
    }
  }
  return `${siteUrl.value}${route.path}`
})

useSeoMeta({
  description: DEFAULT_DESCRIPTION,
  ogSiteName: SITE_NAME,
  ogType: 'website',
  ogImage: () => `${siteUrl.value}${TWITTER_CARD_PATH}`,
  ogImageAlt: TWITTER_CARD_ALT,
  ogImageWidth: 1200,
  ogImageHeight: 630,
  twitterCard: 'summary_large_image',
  twitterImage: () => `${siteUrl.value}${TWITTER_CARD_PATH}`,
  twitterImageAlt: TWITTER_CARD_ALT,
  themeColor: '#09090b',
  colorScheme: 'dark light'
})

useHead(() => ({
  link: canonicalUrl.value
    ? [{ rel: 'canonical', href: canonicalUrl.value }]
    : [],
  script: [
    {
      type: 'application/ld+json',
      innerHTML: JSON.stringify(buildGameJsonLd(siteUrl.value))
    }
  ]
}))

onMounted(loadAccess)
</script>

<template>
  <UApp>
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </UApp>
</template>
