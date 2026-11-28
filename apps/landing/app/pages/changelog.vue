<script setup lang="ts">
import { CHANGELOG_ENTRIES } from '~/data/changelog'

const { t, locale } = useI18n()
const localePath = useLocalePath()
const runtimeConfig = useRuntimeConfig()
const siteUrl = computed(() => String(runtimeConfig.public.siteUrl))

useSeoMeta({
  title: () => t('changelog.seoTitle'),
  description: () => t('changelog.seoDescription'),
  ogTitle: () => `${t('changelog.seoTitle')} | ai-shield`,
  ogDescription: () => t('changelog.seoDescription'),
  ogUrl: () => `${siteUrl.value}${localePath('/changelog')}`,
  robots: 'index, follow'
})

const versions = computed(() => {
  const lang = locale.value === 'ms' ? 'ms' : 'en'
  return CHANGELOG_ENTRIES.map(entry => ({
    title: entry.title[lang],
    description: entry.description[lang],
    date: entry.date,
    badge: `${entry.version} · ${entry.badge}`
  }))
})
</script>

<template>
  <UContainer>
    <UPageHeader
      :title="t('changelog.title')"
      :description="t('changelog.description')"
      class="py-[50px]"
    />

    <UPageBody>
      <UChangelogVersions>
        <UChangelogVersion
          v-for="item in versions"
          :key="item.badge"
          v-bind="item"
        />
      </UChangelogVersions>
    </UPageBody>
  </UContainer>
</template>
