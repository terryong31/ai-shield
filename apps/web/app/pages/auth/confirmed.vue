<script setup lang="ts">
import { buildPageSeo } from '~/utils/seo'

// Landing page for Supabase's confirmation link (spec 0027). Supabase has
// already confirmed the email by the time the browser arrives here, so this
// page reads nothing from the URL and stores nothing.
const runtimeConfig = useRuntimeConfig()
useSeoMeta(buildPageSeo({
  title: 'Email Confirmed',
  description: 'Your ai-shield email address is confirmed. Sign in to save boards and record leaderboard scores.',
  path: '/auth/confirmed',
  siteUrl: runtimeConfig.public.siteUrl,
  noindex: true
}))
</script>

<template>
  <main class="h-full overflow-y-auto">
    <div class="flex min-h-full flex-col items-center justify-center gap-4 p-4">
      <UPageCard class="w-full max-w-md">
        <UEmpty
          icon="i-lucide-badge-check"
          title="Email confirmed"
          description="Your account is ready. Sign in to save boards and record scores."
          variant="naked"
          :actions="[{
            label: 'Sign in',
            to: '/auth/login',
            color: 'neutral',
            variant: 'solid'
          }]"
        />
      </UPageCard>
    </div>
  </main>
</template>
