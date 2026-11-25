<script setup lang="ts">
import { errorDetail } from '~/utils/account'
import { buildPageSeo } from '~/utils/seo'

// Handles Supabase email confirmation and email-change links (spec 0027, 0047).
// Never confirms on GET/SSR; strips sensitive query params immediately on mount
// and calls POST /api/v1/auth/confirm so automated email scanners cannot consume
// the link without a matching browser cookie or explicit user click.
const runtimeConfig = useRuntimeConfig()
useSeoMeta(buildPageSeo({
  title: 'Email Confirmation',
  description: 'Confirm your ai-shield email address to save boards and record leaderboard scores.',
  path: '/auth/confirmed',
  siteUrl: runtimeConfig.public.siteUrl,
  noindex: true
}))

type ConfirmViewState = 'loading' | 'signed_in' | 'confirmation_required' | 'confirmed' | 'error'

const route = useRoute()
const router = useRouter()
const { session, loadingAuth, confirmEmail } = usePlayerAuth()

const viewState = ref<ConfirmViewState>('loading')
const errorMessage = ref('')
const isEmailChange = ref(false)

const pendingPayload = ref<{
  flow_id: string | null
  code: string | null
  token_hash: string | null
  type: 'signup' | 'email_change'
} | null>(null)

const firstParam = (value: unknown): string | null => {
  if (Array.isArray(value)) {
    const first = value[0]
    return typeof first === 'string' && first.trim() ? first.trim() : null
  }
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

const runConfirmation = async (options: { confirm: boolean }) => {
  const payload = pendingPayload.value
  if (!payload) return
  viewState.value = 'loading'
  errorMessage.value = ''
  try {
    const result = await confirmEmail({
      flow_id: payload.flow_id,
      code: payload.code,
      token_hash: payload.token_hash,
      type: payload.type,
      confirm: options.confirm
    })
    if (result.status === 'signed_in') {
      viewState.value = 'signed_in'
    } else if (result.status === 'confirmation_required') {
      viewState.value = 'confirmation_required'
    } else {
      viewState.value = 'confirmed'
    }
  } catch (err) {
    errorMessage.value = errorDetail(err, 'This confirmation link is invalid or has expired.')
    viewState.value = 'error'
  }
}

onMounted(async () => {
  const query = route.query
  const error = firstParam(query.error)
  const errorCode = firstParam(query.error_code)
  const errorDescription = firstParam(query.error_description)
  const code = firstParam(query.code)
  const tokenHash = firstParam(query.token_hash)
  const flowId = firstParam(query.flow)
  const intent = firstParam(query.intent)
  const rawType = firstParam(query.type)
  const type: 'signup' | 'email_change' = rawType === 'email_change' || intent === 'email_change'
    ? 'email_change'
    : 'signup'
  isEmailChange.value = type === 'email_change'

  if (Object.keys(query).length > 0) {
    await router.replace({ path: '/auth/confirmed', query: {} })
  }

  if (error || errorCode) {
    errorMessage.value = errorDescription || 'This confirmation link is invalid or has expired.'
    viewState.value = 'error'
    return
  }

  if (!code && !tokenHash) {
    errorMessage.value = 'This confirmation link is missing required details. Request a new email or sign in.'
    viewState.value = 'error'
    return
  }

  pendingPayload.value = {
    flow_id: flowId,
    code,
    token_hash: tokenHash,
    type
  }
  await runConfirmation({ confirm: false })
})
</script>

<template>
  <main class="h-full overflow-y-auto">
    <div class="flex min-h-full flex-col items-center justify-center gap-4 p-4">
      <UPageCard class="w-full max-w-md">
        <UEmpty
          v-if="viewState === 'loading'"
          icon="i-lucide-loader-circle"
          title="Confirming your email..."
          description="Please wait while we verify your confirmation link."
          variant="naked"
        />

        <UEmpty
          v-else-if="viewState === 'signed_in'"
          icon="i-lucide-badge-check"
          :title="isEmailChange ? 'Email updated' : 'Email confirmed'"
          :description="isEmailChange
            ? `Email updated to ${session.email}.`
            : `You are signed in as ${session.player_name}.`"
          variant="naked"
          :actions="[
            {
              label: 'Continue to game',
              to: '/game',
              color: 'neutral',
              variant: 'solid'
            },
            {
              label: 'Account settings',
              to: '/settings',
              color: 'neutral',
              variant: 'outline'
            }
          ]"
        />

        <UEmpty
          v-else-if="viewState === 'confirmation_required'"
          icon="i-lucide-shield-check"
          title="Confirm your email"
          description="Click below to finish confirming your email. This extra step protects your link from automated email scanners."
          variant="naked"
        >
          <template #actions>
            <UButton
              label="Confirm email"
              color="neutral"
              variant="solid"
              :loading="loadingAuth"
              @click="runConfirmation({ confirm: true })"
            />
          </template>
        </UEmpty>

        <UEmpty
          v-else-if="viewState === 'confirmed'"
          icon="i-lucide-badge-check"
          title="Email confirmed"
          description="Your email is verified. Sign in to continue."
          variant="naked"
          :actions="[{
            label: 'Sign in',
            to: '/auth/login',
            color: 'neutral',
            variant: 'solid'
          }]"
        />

        <UEmpty
          v-else
          icon="i-lucide-mail-warning"
          title="Confirmation failed"
          :description="errorMessage || 'This confirmation link is invalid or has expired.'"
          variant="naked"
          :actions="[
            {
              label: 'Sign in',
              to: '/auth/login',
              color: 'neutral',
              variant: 'solid'
            },
            {
              label: 'Create account',
              to: '/auth/register',
              color: 'neutral',
              variant: 'outline'
            }
          ]"
        />
      </UPageCard>
    </div>
  </main>
</template>
