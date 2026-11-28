<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'

const { t, locale, setLocale } = useI18n()
const localePath = useLocalePath()
const runtimeConfig = useRuntimeConfig()

const open = ref(false)

const playUrl = computed(() => String(runtimeConfig.public.playUrl))

const items = computed<NavigationMenuItem[]>(() => [{
  label: t('nav.pricing'),
  to: localePath('/pricing')
}, {
  label: t('nav.changelog'),
  to: localePath('/changelog')
}])

const otherLocale = computed(() => locale.value === 'en' ? 'ms' : 'en')

function toggleLocale() {
  void setLocale(otherLocale.value)
}
</script>

<template>
  <UHeader v-model:open="open">
    <template #left>
      <NuxtLink
        :to="localePath('/')"
        class="focus-visible:outline-3 outline-primary/25 rounded-md p-1 -ms-1 flex items-center gap-2 font-semibold text-highlighted"
      >
        <img
          src="/favicon.svg"
          alt=""
          aria-hidden="true"
          class="size-6 shrink-0"
        >
        <span>ai-shield</span>
      </NuxtLink>
    </template>

    <UNavigationMenu
      :items="items"
      variant="link"
    />

    <template #right>
      <UButton
        :label="otherLocale === 'ms' ? 'BM' : 'EN'"
        :aria-label="t('nav.switchLanguage')"
        color="neutral"
        variant="ghost"
        @click="toggleLocale"
      />

      <UColorModeButton />

      <UButton
        :label="t('nav.playNow')"
        color="neutral"
        trailing-icon="i-lucide-arrow-right"
        class="hidden lg:inline-flex"
        :to="playUrl"
      />
    </template>

    <template #body>
      <UNavigationMenu
        :items="items"
        orientation="vertical"
        class="-mx-2.5"
      />

      <USeparator class="my-6" />

      <UButton
        :label="t('nav.signIn')"
        color="neutral"
        variant="subtle"
        :to="`${playUrl}/auth/login`"
        block
        class="mb-3"
      />
      <UButton
        :label="t('nav.playNow')"
        color="neutral"
        :to="playUrl"
        block
      />
    </template>
  </UHeader>
</template>
