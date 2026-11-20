<script setup lang="ts">
import type { AuthFormField, FormSubmitEvent } from '@nuxt/ui'
import { registerSchema, type RegisterSchema } from '~/utils/playerAuth'
import { buildPageSeo } from '~/utils/seo'

const runtimeConfig = useRuntimeConfig()
useSeoMeta(buildPageSeo({
  title: 'Create Account',
  description: 'Create a free ai-shield player account to unlock AI safety nodes, save custom defence boards across devices, and compete on the leaderboard.',
  path: '/auth/register',
  siteUrl: runtimeConfig.public.siteUrl
}))

const {
  isLoggedIn,
  loadingAuth,
  refreshSession,
  registerAccount,
  resendConfirmationEmail
} = usePlayerAuth()
const goBack = useGoBack()

// Set once the gateway answers "check your email" (spec 0027).
const sentTo = ref('')

const registerFields: AuthFormField[] = [
  {
    name: 'player_name',
    type: 'text',
    label: 'Player name',
    placeholder: 'DefenderOne',
    defaultValue: '',
    required: true
  },
  {
    name: 'email',
    type: 'email',
    label: 'Email',
    placeholder: 'you@example.com',
    defaultValue: '',
    required: true
  },
  {
    name: 'password',
    type: 'password',
    label: 'Password',
    placeholder: 'At least 8 characters',
    defaultValue: '',
    required: true
  }
]

const onSubmit = async (
  event: FormSubmitEvent<RegisterSchema>
) => {
  const email = event.data.email
  const password = event.data.password
  const outcome = await registerAccount(email, password, event.data.player_name)
  if (outcome === 'signed_in') {
    await goBack('/')
  } else if (outcome === 'confirmation_sent') {
    sentTo.value = email.trim()
  }
}

onMounted(async () => {
  await refreshSession()
  if (isLoggedIn.value) {
    await navigateTo('/', { replace: true })
  }
})
</script>

<template>
  <main class="h-full overflow-y-auto">
    <div class="flex min-h-full flex-col items-center justify-center gap-4 p-4">
      <div class="w-full max-w-md">
        <UButton
          label="Back"
          icon="i-lucide-arrow-left"
          color="neutral"
          variant="link"
          size="xl"
          @click="goBack('/')"
        />
      </div>

      <UPageCard
        v-if="sentTo"
        class="w-full max-w-md"
      >
        <UEmpty
          icon="i-lucide-mail-check"
          title="Check your email"
          variant="naked"
        >
          <template #description>
            We sent a confirmation link to <span class="font-medium text-highlighted">{{ sentTo }}</span>.
            Open it, then sign in.
          </template>

          <template #actions>
            <UButton
              label="Resend email"
              icon="i-lucide-refresh-cw"
              color="neutral"
              variant="outline"
              :loading="loadingAuth"
              @click="resendConfirmationEmail(sentTo)"
            />
            <UButton
              to="/auth/login"
              label="Sign in"
              color="neutral"
              variant="solid"
            />
          </template>
        </UEmpty>
      </UPageCard>

      <UPageCard
        v-else
        class="w-full max-w-md"
      >
        <UAuthForm
          :schema="registerSchema"
          title="Create account"
          icon="i-lucide-user-plus"
          :fields="registerFields"
          :loading="loadingAuth"
          :submit="{
            label: 'Create account',
            color: 'neutral',
            variant: 'solid',
            block: true
          }"
          @submit="onSubmit"
        >
          <template #password-field="{ state }">
            <PasswordStrengthField
              v-model="state.password"
              placeholder="At least 8 characters"
              autocomplete="new-password"
            />
          </template>

          <template #description>
            Already have an account?
            <ULink
              to="/auth/login"
              class="font-medium text-highlighted"
            >Sign in</ULink>.
          </template>
        </UAuthForm>
      </UPageCard>
    </div>
  </main>
</template>
