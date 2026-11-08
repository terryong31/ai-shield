<script setup lang="ts">
import type { AuthFormField, FormSubmitEvent } from '@nuxt/ui'

const {
  isLoggedIn,
  loadingAuth,
  refreshSession,
  signInWithPassword
} = usePlayerAuth()

const loginFields: AuthFormField[] = [
  {
    name: 'email',
    type: 'email',
    label: 'Email',
    placeholder: 'you@example.com',
    required: true
  },
  {
    name: 'password',
    type: 'password',
    label: 'Password',
    placeholder: 'Enter password',
    required: true
  }
]

const onSubmit = async (
  event: FormSubmitEvent<{ email?: string, password?: string }>
) => {
  const email = event.data.email ?? ''
  const password = event.data.password ?? ''
  const succeeded = await signInWithPassword(email, password)
  if (succeeded) {
    await navigateTo('/')
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
  <div class="h-full overflow-y-auto">
    <div class="flex min-h-full flex-col items-center justify-center gap-4 p-4">
      <div class="w-full max-w-md">
        <UButton
          to="/"
          label="Back"
          icon="i-lucide-arrow-left"
          color="neutral"
          variant="link"
          size="xl"
        />
      </div>

      <UPageCard class="w-full max-w-md">
        <UAuthForm
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
  </div>
</template>
