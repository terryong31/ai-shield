<script setup lang="ts">
import type { AuthFormField, FormSubmitEvent } from '@nuxt/ui'

const {
  isLoggedIn,
  loadingAuth,
  refreshSession,
  registerAccount
} = usePlayerAuth()

const registerFields: AuthFormField[] = [
  {
    name: 'player_name',
    type: 'text',
    label: 'Player name',
    placeholder: 'DefenderOne',
    required: true
  },
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
    placeholder: 'At least 6 characters',
    required: true
  }
]

const onSubmit = async (
  event: FormSubmitEvent<{ email?: string, password?: string, player_name?: string }>
) => {
  const email = event.data.email ?? ''
  const password = event.data.password ?? ''
  const succeeded = await registerAccount(email, password, event.data.player_name)
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
  </div>
</template>
