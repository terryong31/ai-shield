<script setup lang="ts">
import { buildPageSeo } from '~/utils/seo'

const event = useRequestEvent()
if (import.meta.server && event) {
  setResponseStatus(event, 404, 'Not Found')
}

const route = useRoute()
const runtimeConfig = useRuntimeConfig()
useSeoMeta(buildPageSeo({
  title: 'Page Not Found',
  description: 'The requested page could not be found on ai-shield.',
  path: route.path,
  siteUrl: runtimeConfig.public.siteUrl,
  noindex: true
}))
</script>

<template>
  <main class="h-full overflow-y-auto">
    <div class="flex min-h-full flex-col items-center justify-center gap-4 p-4">
      <UPageCard class="w-full max-w-md">
        <UEmpty
          icon="i-lucide-compass"
          title="Page not found"
          description="That path does not match any page in ai-shield."
          variant="naked"
          :actions="[{
            label: 'Back to menu',
            to: '/',
            color: 'neutral',
            variant: 'solid'
          }]"
        />
      </UPageCard>
    </div>
  </main>
</template>
