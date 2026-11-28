<script setup lang="ts">
import type { FooterColumn } from '@nuxt/ui'

const { t } = useI18n()
const localePath = useLocalePath()
const runtimeConfig = useRuntimeConfig()

const playUrl = computed(() => String(runtimeConfig.public.playUrl))
const supportEmail = computed(() => String(runtimeConfig.public.supportEmail))

const columns = computed<FooterColumn[]>(() => [{
  label: t('footer.product'),
  children: [{
    label: t('nav.playNow'),
    to: playUrl.value
  }, {
    label: t('nav.pricing'),
    to: localePath('/pricing')
  }, {
    label: t('footer.changelog'),
    to: localePath('/changelog')
  }]
}, {
  label: t('footer.legal'),
  children: [{
    label: t('footer.privacy'),
    to: localePath('/privacy')
  }, {
    label: t('footer.terms'),
    to: localePath('/terms')
  }, {
    label: t('footer.refund'),
    to: localePath('/refund')
  }]
}, {
  label: t('footer.help'),
  children: [{
    label: 'Email Us',
    to: `mailto:${supportEmail.value}`
  }, {
    label: t('footer.security'),
    to: '/.well-known/security.txt',
    external: true,
    target: '_blank'
  }]
}])
</script>

<template>
  <USeparator
    icon="i-lucide-shield-check"
    class="h-px"
  />

  <UFooter :ui="{ top: 'border-b border-default' }">
    <template #top>
      <UContainer>
        <UFooterColumns :columns="columns" />
      </UContainer>
    </template>

    <template #left>
      <p class="text-muted text-sm">
        {{ t('footer.operator') }} © {{ new Date().getFullYear() }}
      </p>
    </template>

    <template #right>
      <UButton
        :to="playUrl"
        icon="i-lucide-gamepad-2"
        :aria-label="t('nav.playNow')"
        color="neutral"
        variant="ghost"
      />
      <UButton
        :to="`mailto:${supportEmail}`"
        icon="i-lucide-mail"
        :aria-label="supportEmail"
        color="neutral"
        variant="ghost"
      />
    </template>
  </UFooter>
</template>
