<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'

const props = defineProps<{
  slug: 'privacy' | 'terms' | 'refund'
}>()

const { t, locale } = useI18n()
const localePath = useLocalePath()
const runtimeConfig = useRuntimeConfig()
const siteUrl = computed(() => String(runtimeConfig.public.siteUrl))
const supportEmail = computed(() => String(runtimeConfig.public.supportEmail))

const { data: page } = await useAsyncData(
  () => `legal-${locale.value}-${props.slug}`,
  () => queryCollection(locale.value === 'ms' ? 'legal_ms' : 'legal_en').path(`/${props.slug}`).first(),
  { watch: [locale] }
)

if (!page.value) {
  throw createError({ statusCode: 404, statusMessage: 'Page not found', fatal: true })
}

const effective = computed(() => page.value
  ? new Intl.DateTimeFormat(locale.value === 'ms' ? 'ms-MY' : 'en-MY', { dateStyle: 'long' }).format(new Date(page.value.effective))
  : '')

const policies = computed<NavigationMenuItem[]>(() => [
  { label: t('footer.privacy'), icon: 'i-lucide-shield-check', to: localePath('/privacy') },
  { label: t('footer.terms'), icon: 'i-lucide-file-text', to: localePath('/terms') },
  { label: t('footer.refund'), icon: 'i-lucide-receipt', to: localePath('/refund') }
])

function printPage() {
  window.print()
}

useSeoMeta({
  title: () => page.value?.title,
  description: () => page.value?.description,
  ogTitle: () => `${page.value?.title} | ai-shield`,
  ogDescription: () => page.value?.description,
  ogUrl: () => `${siteUrl.value}${localePath(`/${props.slug}`)}`,
  robots: 'index, follow'
})
</script>

<template>
  <UContainer v-if="page">
    <UPage>
      <template #left>
        <UPageAside class="print:hidden">
          <p class="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">
            {{ t('legal.policies') }}
          </p>
          <UNavigationMenu
            :items="policies"
            orientation="vertical"
            color="neutral"
            highlight
            highlight-color="neutral"
            class="-mx-2.5"
          />
        </UPageAside>
      </template>

      <UPageHeader
        :title="page.title"
        :description="page.description"
        :headline="t('legal.headline')"
      >
        <template #links>
          <UButton
            :label="t('legal.print')"
            icon="i-lucide-printer"
            color="neutral"
            variant="outline"
            class="print:hidden"
            @click="printPage"
          />
        </template>

        <div class="mt-4 flex flex-wrap gap-2">
          <UBadge
            :label="`${t('legal.effective')} ${effective}`"
            icon="i-lucide-calendar"
            color="neutral"
            variant="subtle"
          />
          <UBadge
            :label="`${t('legal.version')} ${page.version}`"
            icon="i-lucide-git-commit-horizontal"
            color="neutral"
            variant="subtle"
          />
        </div>
      </UPageHeader>

      <UPageBody>
        <section
          :aria-label="t('legal.atAGlance')"
          class="not-prose"
        >
          <h2 class="mb-4 text-lg font-semibold text-highlighted">
            {{ t('legal.atAGlance') }}
          </h2>
          <UPageGrid :class="page.summary.length === 3 ? 'lg:grid-cols-3 xl:grid-cols-3' : 'lg:grid-cols-2 xl:grid-cols-2'">
            <UPageCard
              v-for="item in page.summary"
              :key="item.to"
              :title="item.title"
              :description="item.description"
              :icon="item.icon"
              :to="item.to"
              variant="subtle"
            />
          </UPageGrid>
        </section>

        <USeparator class="my-10" />

        <ContentRenderer :value="page" />

        <USeparator class="my-10" />

        <UPageCard
          :title="t('legal.questionsTitle')"
          :description="t('legal.questionsBody')"
          icon="i-lucide-mail"
          variant="subtle"
          class="print:hidden"
        >
          <template #footer>
            <UButton
              :label="supportEmail"
              :to="`mailto:${supportEmail}`"
              color="neutral"
              trailing-icon="i-lucide-arrow-right"
            />
          </template>
        </UPageCard>
      </UPageBody>

      <template
        v-if="page.body?.toc?.links?.length"
        #right
      >
        <UContentToc
          :title="t('legal.onThisPage')"
          :links="page.body.toc.links"
          color="neutral"
          highlight
          highlight-color="neutral"
          class="print:hidden"
        />
      </template>
    </UPage>
  </UContainer>
</template>
