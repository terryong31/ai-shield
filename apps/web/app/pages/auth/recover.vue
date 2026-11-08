<script setup lang="ts">
import type { AuthFormField, FormSubmitEvent } from '@nuxt/ui'

const {
  isLoggedIn,
  loadingAuth,
  refreshSession,
  recoverPassword
} = usePlayerAuth()

const recoverFields: AuthFormField[] = [
  {
    name: 'email',
    type: 'email',
    label: 'Email',
    placeholder: 'you@example.com',
    required: true
  }
]

const onSubmit = async (
  event: FormSubmitEvent<{ email?: string }>
) => {
  const email = event.data.email ?? ''
  const succeeded = await recoverPassword(email)
  if (succeeded) {
    await navigateTo('/auth/login')
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
          to="/auth/login"
          label="Back"
          icon="i-lucide-arrow-left"
          color="neutral"
          variant="link"
          size="xl"
        />
      </div>

      <UPageCard class="w-full max-w-md">
        <UAuthForm
          title="Recover password"
          icon="i-lucide-key-round"
          :fields="recoverFields"
          :loading="loadingAuth"
          :submit="{
            label: 'Send recovery email',
            color: 'neutral',
            variant: 'solid',
            block: true
          }"
          @submit="onSubmit"
        >
          <template #description>
            Remember your password?
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
