<script setup lang="ts">
const colorMode = useColorMode()
const head = useLocaleHead({ seo: true })

const color = computed(() => colorMode.value === 'dark' ? '#171717' : 'white')

useHead(() => ({
  meta: [
    { key: 'theme-color', name: 'theme-color', content: color.value }
  ],
  htmlAttrs: {
    lang: head.value.htmlAttrs?.lang || 'en'
  }
}))

useSeoMeta({
  twitterCard: 'summary_large_image'
})
</script>

<template>
  <UApp>
    <Head>
      <template
        v-for="link in head.link"
        :key="`${link.hreflang || link.rel}-${link.href}`"
      >
        <Link
          :rel="link.rel"
          :href="link.href"
          :hreflang="link.hreflang"
        />
      </template>
    </Head>

    <NuxtRouteAnnouncer />
    <NuxtLoadingIndicator />

    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </UApp>
</template>
