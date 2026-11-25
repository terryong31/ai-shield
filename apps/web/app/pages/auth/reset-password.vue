<script setup lang="ts">
import type { FormSubmitEvent } from '@nuxt/ui'
import { resetPasswordSchema, type ResetPasswordSchema } from '~/utils/playerAuth'
import { buildPageSeo } from '~/utils/seo'

const runtimeConfig = useRuntimeConfig()
useSeoMeta(buildPageSeo({
  title: 'Reset Password',
  description: 'Set a new password for your ai-shield player account.',
  path: '/auth/reset-password',
  siteUrl: runtimeConfig.public.siteUrl,
  noindex: true
}))

const route = useRoute()
const router = useRouter()
const { loadingAuth, resetPassword } = usePlayerAuth()

const form = reactive({
  password: '',
  confirm: ''
})

const invalidLink = ref(false)
const invalidMessage = ref('')
const tokenPayload = ref<{
  flow_id: string | null
  code: string | null
  token_hash: string | null
} | null>(null)

const firstParam = (value: unknown): string | null => {
  if (Array.isArray(value)) {
    const first = value[0]
    return typeof first === 'string' && first.trim() ? first.trim() : null
  }
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

const onSubmit = async (event: FormSubmitEvent<ResetPasswordSchema>) => {
  const payload = tokenPayload.value
  if (!payload) return
  const ok = await resetPassword({
    flow_id: payload.flow_id,
    code: payload.code,
    token_hash: payload.token_hash,
    new_password: event.data.password
  })
  if (ok) {
    await navigateTo('/auth/login', { replace: true })
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

  if (Object.keys(query).length > 0) {
    await router.replace({ path: '/auth/reset-password', query: {} })
  }

  if (error || errorCode || (!code && !tokenHash)) {
    invalidMessage.value = errorDescription || 'This recovery link is invalid or has expired.'
    invalidLink.value = true
    return
  }

  tokenPayload.value = {
    flow_id: flowId,
    code,
    token_hash: tokenHash
  }
})
</script>

<template>
  <main class="h-full overflow-y-auto">
    <div class="flex min-h-full flex-col items-center justify-center gap-4 p-4">
      <UPageCard class="w-full max-w-md">
        <UEmpty
          v-if="invalidLink"
          icon="i-lucide-mail-warning"
          title="Recovery link expired"
          :description="invalidMessage"
          variant="naked"
          :actions="[{
            label: 'Request new link',
            to: '/auth/recover',
            color: 'neutral',
            variant: 'solid'
          }]"
        />

        <div
          v-else
          class="space-y-4"
        >
          <div class="space-y-1 text-center">
            <h1 class="text-xl font-semibold text-highlighted">
              Set a new password
            </h1>
            <p class="text-sm text-muted">
              Choose a strong password for your account. All existing sessions will be signed out.
            </p>
          </div>

          <UForm
            :schema="resetPasswordSchema"
            :state="form"
            class="space-y-4"
            @submit="onSubmit"
          >
            <UFormField
              label="New password"
              name="password"
              required
            >
              <PasswordStrengthField
                id="reset-new-password"
                v-model="form.password"
                placeholder="At least 8 characters"
                autocomplete="new-password"
              />
            </UFormField>

            <UFormField
              label="Confirm new password"
              name="confirm"
              required
            >
              <UInput
                v-model="form.confirm"
                type="password"
                autocomplete="new-password"
                placeholder="Repeat your new password"
                class="w-full"
              />
            </UFormField>

            <UButton
              type="submit"
              label="Update password"
              color="neutral"
              variant="solid"
              block
              :loading="loadingAuth"
            />
          </UForm>
        </div>
      </UPageCard>
    </div>
  </main>
</template>
