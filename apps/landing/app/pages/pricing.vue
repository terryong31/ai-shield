<script setup lang="ts">
import { PRICING, PROVIDER_ICONS } from '~/data/pricing'

const { locale } = useI18n()
const localePath = useLocalePath()
const runtimeConfig = useRuntimeConfig()

const playUrl = computed(() => String(runtimeConfig.public.playUrl))
const siteUrl = computed(() => String(runtimeConfig.public.siteUrl))
const page = computed(() => PRICING[locale.value === 'ms' ? 'ms' : 'en'])

const plans = computed(() => page.value.plans.map(({ id, button, ...plan }) => ({
  ...plan,
  button: id === 'pass'
    ? { label: button, to: `${playUrl.value}/plans`, color: 'neutral' as const }
    : { label: button, to: playUrl.value, color: 'neutral' as const, variant: 'subtle' as const }
})))

useSeoMeta({
  title: () => page.value.seo.title,
  ogTitle: () => `${page.value.seo.title} | ai-shield`,
  description: () => page.value.seo.description,
  ogDescription: () => page.value.seo.description,
  ogUrl: () => `${siteUrl.value}${localePath('/pricing')}`,
  robots: 'index, follow'
})
</script>

<template>
  <div>
    <UPageHero
      :title="page.title"
      :description="page.description"
    />

    <UContainer>
      <UPricingPlans
        scale
        class="max-w-4xl mx-auto"
      >
        <UPricingPlan
          v-for="(plan, index) in plans"
          :key="index"
          v-bind="plan"
        />
      </UPricingPlans>
    </UContainer>

    <UPageSection :title="page.logos.title">
      <UPageLogos>
        <UIcon
          v-for="icon in PROVIDER_ICONS"
          :key="icon"
          :name="icon"
          class="w-12 h-12 shrink-0 text-muted"
        />
      </UPageLogos>
    </UPageSection>

    <UPageSection
      :title="page.faq.title"
      :description="page.faq.description"
    >
      <UAccordion
        :items="page.faq.items"
        :unmount-on-hide="false"
        :default-value="['0']"
        type="multiple"
        class="max-w-3xl mx-auto"
        :ui="{
          trigger: 'text-base text-highlighted',
          body: 'text-base text-muted'
        }"
      />
    </UPageSection>
  </div>
</template>
