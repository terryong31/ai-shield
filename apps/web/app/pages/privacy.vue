<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import { buildPageSeo } from '~/utils/seo'

// Privacy policy (spec 0058). Every fact here comes from the code: keep it in step when
// a table, cookie, storage key or provider changes.
const runtimeConfig = useRuntimeConfig()
useSeoMeta({
  ...buildPageSeo({
    title: 'Privacy Policy',
    description: 'What ai-shield collects, why, where it is kept, for how long, and how to download or delete your data.',
    path: '/privacy',
    siteUrl: runtimeConfig.public.siteUrl
  }),
  robots: 'index, follow'
})

const goBack = useGoBack()
const contactEmail = computed(() => String(runtimeConfig.public.privacyContactEmail || ''))
const ISSUES_URL = 'https://github.com/terryong31/ai-shield/issues'

const EFFECTIVE_DATE = '27 November 2026'
const POLICY_VERSION = '1.0'

interface Row {
  name: string
  detail: string
  purpose: string
  kept: string
}

const columns = (first: string, second: string): TableColumn<Row>[] => [
  { accessorKey: 'name', header: first },
  { accessorKey: 'detail', header: second },
  { accessorKey: 'purpose', header: 'Why' },
  { accessorKey: 'kept', header: 'How long' }
]

const dataRows: Row[] = [
  {
    name: 'Account',
    detail: 'Email (lowercase), display name, plan (free or paid), pass end date, account creation date',
    purpose: 'Sign-in, daily limits for your plan, and your place on the leaderboard',
    kept: 'Until you delete your account'
  },
  {
    name: 'Progress',
    detail: 'Saved boards, best scores and medals, the CSV rows you upload to train the ML filter',
    purpose: 'Keep your progress across devices, rank the leaderboard, run your ML filter',
    kept: 'Boards and scores until you reset progress or delete your account. A trained model stays in memory only, for 30 minutes after its last use'
  },
  {
    name: 'Anonymous play',
    detail: 'Best scores of a session that is not signed in, keyed by a hash of its session token',
    purpose: 'Move your scores to your account when you sign in',
    kept: '7 days, or until you sign in'
  },
  {
    name: 'Prompts and your own API keys',
    detail: 'The prompts of a wave, and the API key you type in the Custom sandbox',
    purpose: 'Run the checks and the agent for that one run',
    kept: 'Not stored. Your API key stays in the page memory only'
  },
  {
    name: 'Payments',
    detail: 'Pass purchases: id, amount, currency, status, payment id, start and end dates',
    purpose: 'Grant 30-day passes and handle refunds and disputes. Card details stay with Stripe',
    kept: 'Kept for accounting. Your email is removed from them when you delete your account'
  },
  {
    name: 'Security',
    detail: 'Hashed IP addresses in rate-limit counters, hashed session tokens, daily run counts, audit records with a hash of your email',
    purpose: 'Stop brute force, bots and abuse',
    kept: 'Rate-limit counters: 1 minute to 1 hour. Daily run counts of a deleted account: 30 days'
  },
  {
    name: 'Site measurement',
    detail: 'Page views and page speed, with no query string on sign-in pages',
    purpose: 'Check that the site is available and fast',
    kept: 'As set by Vercel'
  }
]

const storageRows: Row[] = [
  { name: 'shield_player_session', detail: 'HttpOnly cookie', purpose: 'Your session, signed in or anonymous. The server keeps only its hash', kept: '8 hours, or until you sign out' },
  { name: 'shield_auth_browser', detail: 'HttpOnly cookie', purpose: 'Connects an email link to the browser that asked for it', kept: '30 to 60 minutes' },
  { name: 'shield_session_hint', detail: 'Cookie', purpose: 'Shows the right menu on the first load. Holds no email or token', kept: 'Same as your session' },
  { name: 'shield_session', detail: 'HttpOnly cookie, SameSite=Strict', purpose: 'Admin console access, for operators only', kept: '8 hours' },
  { name: 'shield_anon_draft:v1:<level>', detail: 'localStorage', purpose: 'Your board on a level before you sign in. Holds no score', kept: 'Until Restart, sign-in, or you clear site data' },
  { name: 'ai-shield:tour-seen:<level>', detail: 'localStorage', purpose: 'Remembers that you saw a level tour', kept: 'Until you clear site data' },
  { name: 'Saved board and leaderboard cache', detail: 'sessionStorage', purpose: 'Faster loading in this tab', kept: 'Until you close the tab' }
]

const processorRows: Row[] = [
  { name: 'Supabase', detail: 'Database and sign-in', purpose: 'Stores accounts, progress and payments; checks passwords', kept: 'As above' },
  { name: 'Vercel', detail: 'Hosting, BotID, Web Analytics, Speed Insights', purpose: 'Serves the site and blocks bots', kept: 'As set by Vercel' },
  { name: 'Redis (Upstash)', detail: 'Short-lived counters and caches', purpose: 'Rate limits, email-link state, leaderboard cache, trained models', kept: 'Minutes to 2 days' },
  { name: 'Stripe', detail: 'Hosted checkout', purpose: 'Takes payments for passes', kept: 'As set by Stripe' },
  { name: 'Google (Gemini) and Groq', detail: 'AI models', purpose: 'Run the protected agent on Medium and Hard levels', kept: 'Prompts of a run, as set by the provider' },
  { name: 'TypeSafe', detail: 'Jev check', purpose: 'Scores a prompt when you use the Jev node', kept: 'Prompts of a run, as set by the provider' },
  { name: 'Your model provider', detail: 'OpenAI, Anthropic, Google, Groq, DeepSeek, Qwen or Moonshot', purpose: 'Runs the Custom sandbox with the API key you give', kept: 'As set by that provider' }
]

// Long policy text wraps in its cell instead of scrolling the table sideways.
const tableUi = { td: 'whitespace-normal align-top text-sm', th: 'whitespace-nowrap' }

const rights = [
  { title: 'Download your data', text: 'In Settings, use Download my data. You get a JSON file with your account, saved boards, scores and purchases.', to: '/settings' },
  { title: 'Correct your data', text: 'In Settings, change your display name, email or password.', to: '/settings' },
  { title: 'Reset your progress', text: 'In Settings, Reset progress deletes your scores and saved boards.', to: '/settings' },
  { title: 'Delete your account', text: 'In Settings, Delete account removes your account, progress and sessions, and removes your email from payment records.', to: '/settings' }
]
</script>

<template>
  <main class="h-full overflow-y-auto">
    <div class="mx-auto flex w-full max-w-4xl flex-col gap-8 p-4 pb-16">
      <div class="flex items-center gap-3">
        <UButton
          label="Back"
          icon="i-lucide-arrow-left"
          color="neutral"
          variant="link"
          size="xl"
          class="text-base"
          @click="goBack('/')"
        />
      </div>

      <UPageHeader
        title="Privacy Policy"
        :description="`Effective ${EFFECTIVE_DATE}. Policy version ${POLICY_VERSION}.`"
      />

      <UPageCard
        title="Summary"
        variant="subtle"
      >
        <p class="text-sm text-default">
          ai-shield is a game about prompt injection. We collect only what the game needs: your
          account, your progress, your payments and what keeps the service safe. We do not sell
          your data, and we do not store the prompts of a run or your own API keys.
        </p>
        <p class="text-sm text-default">
          The operator of ai-shield controls this data. For a privacy question, write to
          <ULink
            v-if="contactEmail"
            :to="`mailto:${contactEmail}`"
          >{{ contactEmail }}</ULink>
          <ULink
            v-else
            :to="ISSUES_URL"
            target="_blank"
          >the project issues page</ULink>.
        </p>
      </UPageCard>

      <section class="space-y-3">
        <h2 class="text-lg font-semibold text-highlighted">
          Data we collect
        </h2>
        <UTable
          :data="dataRows"
          :columns="columns('Category', 'Data')"
          :ui="tableUi"
          class="rounded-md border border-default"
        />
      </section>

      <section class="space-y-3">
        <h2 class="text-lg font-semibold text-highlighted">
          Cookies and browser storage
        </h2>
        <p class="text-sm text-muted">
          These are needed for the game to work. There are no advertising cookies.
        </p>
        <UTable
          :data="storageRows"
          :columns="columns('Name', 'Kind')"
          :ui="tableUi"
          class="rounded-md border border-default"
        />
      </section>

      <section class="space-y-3">
        <h2 class="text-lg font-semibold text-highlighted">
          Sub-processors
        </h2>
        <UTable
          :data="processorRows"
          :columns="columns('Company', 'Service')"
          :ui="tableUi"
          class="rounded-md border border-default"
        />
      </section>

      <UPageCard
        title="Retention and deletion"
        variant="subtle"
      >
        <p class="text-sm text-default">
          We keep your account data until you delete your account. When you delete it, we
          delete your saved boards, scores, sessions, trained models, account and sign-in
          record, and we remove your email from payment records. Daily run counts older than
          30 days are deleted with the account.
        </p>
      </UPageCard>

      <section class="space-y-3">
        <h2 class="text-lg font-semibold text-highlighted">
          Your rights
        </h2>
        <div class="grid gap-3 sm:grid-cols-2">
          <UPageCard
            v-for="right in rights"
            :key="right.title"
            :title="right.title"
            :description="right.text"
            :to="right.to"
            variant="outline"
          />
        </div>
        <p class="text-sm text-muted">
          ai-shield is not for children under 13, or under the minimum age for digital consent
          where you live.
        </p>
      </section>
    </div>
  </main>
</template>
