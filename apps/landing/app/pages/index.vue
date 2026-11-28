<script setup lang="ts">
import { HOME } from '~/data/home'

const { locale } = useI18n()
const localePath = useLocalePath()
const runtimeConfig = useRuntimeConfig()

const playUrl = computed(() => String(runtimeConfig.public.playUrl))
const siteUrl = computed(() => String(runtimeConfig.public.siteUrl))
const page = computed(() => HOME[locale.value === 'ms' ? 'ms' : 'en'])

const heroTitle = computed(() => {
  const title = page.value.title
  const highlight = page.value.highlight
  const index = title.indexOf(highlight)

  if (index === -1) {
    return
  }

  return {
    before: title.slice(0, index),
    highlight,
    after: title.slice(index + highlight.length)
  }
})

const heroLinks = computed(() => [{
  label: page.value.heroPrimary,
  icon: 'i-lucide-arrow-right',
  trailing: true,
  to: playUrl.value,
  size: 'xl' as const,
  color: 'neutral' as const
}])

const ctaLinks = computed(() => [{
  label: page.value.cta.primary,
  to: playUrl.value,
  color: 'neutral' as const,
  trailingIcon: 'i-lucide-arrow-right'
}, {
  label: page.value.cta.secondary,
  to: localePath('/changelog'),
  color: 'neutral' as const,
  variant: 'subtle' as const,
  icon: 'i-lucide-history'
}])

useSeoMeta({
  title: () => page.value.seo.title,
  ogTitle: () => `${page.value.seo.title} | ai-shield`,
  description: () => page.value.seo.description,
  ogDescription: () => page.value.seo.description,
  ogUrl: () => `${siteUrl.value}${localePath('/')}`,
  ogType: 'website',
  robots: 'index, follow'
})
</script>

<template>
  <div>
    <UPageHero
      :title="page.title"
      :description="page.description"
      :links="heroLinks"
    >
      <template #top>
        <HeroBackground />
      </template>

      <template
        v-if="heroTitle"
        #title
      >
        {{ heroTitle.before }}<span class="text-primary">{{ heroTitle.highlight }}</span>{{ heroTitle.after }}
      </template>

      <PromotionalVideo :alt="page.videoAlt" />
    </UPageHero>

    <UPageSection
      v-for="section in page.sections"
      :id="section.id"
      :key="section.id"
      :title="section.title"
      :description="section.description"
      :orientation="section.orientation"
      :reverse="section.reverse"
      :features="section.features"
    >
      <ScreenshotCard
        :src="section.image.src"
        :alt="section.image.alt"
      />
    </UPageSection>

    <UPageSection
      :title="page.features.title"
      :description="page.features.description"
    >
      <UPageGrid>
        <UPageCard
          v-for="(item, index) in page.features.items"
          :key="index"
          v-bind="item"
          spotlight
        />
      </UPageGrid>
    </UPageSection>

    <UPageSection
      id="attacks"
      :headline="page.attacks.headline"
      :title="page.attacks.title"
      :description="page.attacks.description"
    >
      <UPageColumns class="xl:columns-4">
        <UPageCard
          v-for="(attack, index) in page.attacks.items"
          :key="index"
          variant="subtle"
          :description="attack.quote"
          :ui="{ description: 'before:content-[open-quote] after:content-[close-quote]' }"
        >
          <template #footer>
            <UUser
              :name="attack.family"
              :description="attack.level"
              :avatar="{ icon: attack.icon }"
              size="lg"
            />
          </template>
        </UPageCard>
      </UPageColumns>
    </UPageSection>

    <USeparator />

    <UPageCTA
      :title="page.cta.title"
      :description="page.cta.description"
      :links="ctaLinks"
      variant="naked"
      class="overflow-hidden"
    >
      <LazyStarsBg />
    </UPageCTA>
  </div>
</template>
