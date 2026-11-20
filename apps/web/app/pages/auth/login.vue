<script setup lang="ts">
import type { AuthFormField, FormSubmitEvent } from '@nuxt/ui'
import { loginSchema, type LoginSchema } from '~/utils/playerAuth'
import { buildPageSeo } from '~/utils/seo'

const runtimeConfig = useRuntimeConfig()
useSeoMeta(buildPageSeo({
  title: 'Sign In',
  description: 'Sign in to your ai-shield player account to unlock AI defence nodes, save board workflows, and record scores on the leaderboard.',
  path: '/auth/login',
  siteUrl: runtimeConfig.public.siteUrl
}))

const {
  isLoggedIn,
  loadingAuth,
  refreshSession,
  signInWithPassword,
  resendConfirmationEmail
} = usePlayerAuth()
const goBack = useGoBack()

// The email of a sign-in refused because it is not confirmed yet (spec 0027).
const unconfirmedEmail = ref('')

const loginFields: AuthFormField[] = [
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
    placeholder: 'Enter password',
    defaultValue: '',
    required: true
  }
]

const onSubmit = async (
  event: FormSubmitEvent<LoginSchema>
) => {
  const email = event.data.email
  const password = event.data.password
  const outcome = await signInWithPassword(email, password)
  unconfirmedEmail.value = outcome === 'unconfirmed' ? email.trim() : ''
  const succeeded = outcome === 'signed_in'
  if (succeeded) {
    await goBack('/')
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

      <UPageCard class="w-full max-w-md">
        <UAuthForm
          :schema="loginSchema"
          title="Sign in"
          icon="i-lucide-user"
          :fields="loginFields"
          :loading="loadingAuth"
          :submit="{
            label: 'Sign in',
            color: 'neutral',
            variant: 'solid',
            block: true
          }"
          @submit="onSubmit"
        >
          <template #validation>
            <UAlert
              v-if="unconfirmedEmail"
              color="warning"
              variant="subtle"
              icon="i-lucide-mail-warning"
              title="Confirm your email first"
              :description="`Open the link we sent to ${unconfirmedEmail}, then sign in.`"
            >
              <template #actions>
                <UButton
                  label="Resend email"
                  color="neutral"
                  variant="outline"
                  size="sm"
                  :loading="loadingAuth"
                  @click="resendConfirmationEmail(unconfirmedEmail)"
                />
              </template>
            </UAlert>
          </template>

          <template #description>
            New to ai-shield?
            <ULink
              to="/auth/register"
              class="font-medium text-highlighted"
            >Create an account</ULink>.
          </template>

          <template #password-hint>
            <ULink
              to="/auth/recover"
              class="font-medium text-highlighted"
              tabindex="-1"
            >Forgot password?</ULink>
          </template>
        </UAuthForm>
      </UPageCard>
    </div>
  </main>
</template>
