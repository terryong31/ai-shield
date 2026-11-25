<script setup lang="ts">
import { deleteConfirmed, displayNameSchema, errorDetail, passwordChangeReady } from '~/utils/account'
import { ensureAuthBrowserCookie, passwordChangeSchema } from '~/utils/playerAuth'
import { buildPageSeo } from '~/utils/seo'

const runtimeConfig = useRuntimeConfig()
useSeoMeta(buildPageSeo({
  title: 'Settings',
  description: 'Manage your ai-shield theme preference, account email, password, and saved game progress.',
  path: '/settings',
  siteUrl: runtimeConfig.public.siteUrl,
  noindex: true
}))

const goBack = useGoBack()
const toast = useToast()
const { session, isLoggedIn, refreshSession, continueAnonymously } = usePlayerAuth()
const { refreshScores } = useLeaderboard()
const { changeDisplayName, changePassword, changeEmail, resetProgress, deleteAccount } = useShieldApi()

// Account settings (spec 0025). Every action except the display name asks for the current password.
type AccountModal = 'name' | 'email' | 'password' | 'reset' | 'delete'
const openModal = ref<AccountModal | null>(null)
const busy = ref(false)
const formError = ref('')

const nameForm = reactive({ name: '' })
const emailForm = reactive({ email: '', password: '' })
const passwordForm = reactive({ current: '', next: '', confirm: '' })
const resetForm = reactive({ password: '' })
const deleteForm = reactive({ password: '', confirm: '' })

const modalOpen = (name: AccountModal) => computed({
  get: () => openModal.value === name,
  set: (open: boolean) => {
    openModal.value = open ? name : null
  }
})
const isNameOpen = modalOpen('name')
const isEmailOpen = modalOpen('email')
const isPasswordOpen = modalOpen('password')
const isResetOpen = modalOpen('reset')
const isDeleteOpen = modalOpen('delete')

const open = (name: AccountModal) => {
  Object.assign(nameForm, { name: session.value.player_name })
  Object.assign(emailForm, { email: '', password: '' })
  Object.assign(passwordForm, { current: '', next: '', confirm: '' })
  Object.assign(resetForm, { password: '' })
  Object.assign(deleteForm, { password: '', confirm: '' })
  formError.value = ''
  openModal.value = name
}

const run = async (action: () => Promise<void>) => {
  busy.value = true
  formError.value = ''
  try {
    await action()
  } catch (err) {
    formError.value = errorDetail(err)
  } finally {
    busy.value = false
  }
}

const submitName = () => run(async () => {
  session.value = await changeDisplayName({ player_name: nameForm.name.trim() })
  void refreshScores({ background: true })
  openModal.value = null
  toast.add({ title: 'Display name changed', icon: 'i-lucide-user-check', color: 'neutral' })
})

const submitEmail = () => run(async () => {
  ensureAuthBrowserCookie()
  await changeEmail({
    new_email: emailForm.email.trim(),
    current_password: emailForm.password
  })
  openModal.value = null
  toast.add({
    title: 'Confirmation sent',
    description: 'Check both your current and new inboxes to confirm the change, then sign in with your new address.',
    icon: 'i-lucide-mail-check',
    color: 'neutral'
  })
})

const submitPassword = () => run(async () => {
  session.value = await changePassword({
    current_password: passwordForm.current,
    new_password: passwordForm.next
  })
  openModal.value = null
  toast.add({ title: 'Password changed', description: 'Your other devices have been signed out.', icon: 'i-lucide-key-round', color: 'neutral' })
})

const submitReset = () => run(async () => {
  const removed = await resetProgress({ current_password: resetForm.password })
  useSavedBoardCache().clearSavedBoardCache()
  void refreshScores({ background: true })
  openModal.value = null
  toast.add({
    title: 'Progress reset',
    description: `Removed ${removed.scores_removed} scores and ${removed.boards_removed} saved boards.`,
    icon: 'i-lucide-rotate-ccw',
    color: 'neutral'
  })
})

const submitDelete = () => run(async () => {
  await deleteAccount({ current_password: deleteForm.password, confirm: 'DELETE' })
  useSavedBoardCache().clearSavedBoardCache()
  void refreshScores({ background: true })
  openModal.value = null
  toast.add({ title: 'Account deleted', icon: 'i-lucide-trash-2', color: 'neutral' })
  await continueAnonymously()
  await navigateTo('/', { replace: true })
})

onMounted(() => {
  void refreshSession()
})
</script>

<template>
  <main class="h-full overflow-y-auto">
    <div class="flex min-h-full w-full items-center justify-center gap-4 p-4">
      <div class="flex flex-col items-center gap-3">
        <div class="flex items-center justify-start gap-3 w-full">
          <UButton
            label="Back"
            icon="i-lucide-arrow-left"
            color="neutral"
            variant="link"
            size="xl"
            class="text-base"
            @click="goBack('/')"
          />
          <h1 class="text-base font-bold uppercase tracking-wider text-highlighted">
            Settings
          </h1>
        </div>
        <UPageCard class="w-full max-w-md min-w-190">
          <div class="flex items-center justify-between gap-4">
            <span class="text-base font-medium text-highlighted">
              Theme
            </span>
            <UColorModeSelect size="lg" />
          </div>
        </UPageCard>

        <UPageCard
          v-if="isLoggedIn"
          title="Account"
          class="w-full max-w-md min-w-190"
        >
          <div class="divide-y divide-default">
            <div class="flex items-center justify-between gap-4 py-3 first:pt-0">
              <div class="min-w-0">
                <p class="text-base font-medium text-highlighted">
                  Display name
                </p>
                <p class="truncate text-sm text-muted">
                  {{ session.player_name }}
                </p>
              </div>
              <UButton
                label="Change"
                color="neutral"
                variant="outline"
                @click="open('name')"
              />
            </div>
            <div class="flex items-center justify-between gap-4 py-3">
              <div class="min-w-0">
                <p class="text-base font-medium text-highlighted">
                  Email
                </p>
                <p class="truncate text-sm text-muted">
                  {{ session.email }}
                </p>
              </div>
              <UButton
                label="Change"
                color="neutral"
                variant="outline"
                @click="open('email')"
              />
            </div>
            <div class="flex items-center justify-between gap-4 py-3">
              <p class="text-base font-medium text-highlighted">
                Password
              </p>
              <UButton
                label="Change"
                color="neutral"
                variant="outline"
                @click="open('password')"
              />
            </div>
            <div class="flex items-center justify-between gap-4 py-3">
              <div>
                <p class="text-base font-medium text-highlighted">
                  Reset progress
                </p>
                <p class="text-sm text-muted">
                  Remove your scores and saved boards.
                </p>
              </div>
              <UButton
                label="Reset"
                color="warning"
                variant="soft"
                @click="open('reset')"
              />
            </div>
            <div class="flex items-center justify-between gap-4 py-3 last:pb-0">
              <div>
                <p class="text-base font-medium text-highlighted">
                  Delete account
                </p>
                <p class="text-sm text-muted">
                  Remove your account and everything in it.
                </p>
              </div>
              <UButton
                label="Delete"
                color="error"
                variant="soft"
                @click="open('delete')"
              />
            </div>
          </div>
        </UPageCard>

        <UPageCard
          v-else
          title="Account"
          class="w-full max-w-md min-w-190"
        >
          <UButton
            label="Sign in to manage your account"
            to="/auth/login"
            icon="i-lucide-log-in"
            color="neutral"
            variant="outline"
            block
            size="lg"
          />
        </UPageCard>
      </div>
    </div>

    <UModal
      v-model:open="isNameOpen"
      title="Change display name"
      description="This name shows on the leaderboard."
    >
      <template #body>
        <UForm
          :schema="displayNameSchema"
          :state="nameForm"
          class="space-y-4"
          @submit="submitName"
        >
          <UFormField
            label="Display name"
            name="name"
            required
          >
            <UInput
              v-model="nameForm.name"
              autocomplete="nickname"
              :maxlength="64"
              class="w-full"
            />
          </UFormField>
          <UAlert
            v-if="formError"
            color="neutral"
            variant="subtle"
            icon="i-lucide-triangle-alert"
            :description="formError"
          />
          <UButton
            type="submit"
            label="Save"
            color="neutral"
            block
            :loading="busy"
          />
        </UForm>
      </template>
    </UModal>

    <UModal
      v-model:open="isEmailOpen"
      title="Change email"
      description="You will sign in with the new address. Your scores and saved boards move with it."
    >
      <template #body>
        <UForm
          :state="emailForm"
          class="space-y-4"
          @submit="submitEmail"
        >
          <UFormField
            label="New email"
            name="email"
            required
          >
            <UInput
              v-model="emailForm.email"
              type="email"
              autocomplete="email"
              class="w-full"
            />
          </UFormField>
          <UFormField
            label="Current password"
            name="password"
            required
          >
            <UInput
              v-model="emailForm.password"
              type="password"
              autocomplete="current-password"
              class="w-full"
            />
          </UFormField>
          <UAlert
            v-if="formError"
            color="neutral"
            variant="subtle"
            icon="i-lucide-triangle-alert"
            :description="formError"
          />
          <UButton
            type="submit"
            label="Change email"
            color="neutral"
            block
            :loading="busy"
            :disabled="!emailForm.email.trim() || !emailForm.password"
          />
        </UForm>
      </template>
    </UModal>

    <UModal
      v-model:open="isPasswordOpen"
      title="Change password"
      description="Your other devices will be signed out."
    >
      <template #body>
        <UForm
          :schema="passwordChangeSchema"
          :state="passwordForm"
          class="space-y-4"
          @submit="submitPassword"
        >
          <UFormField
            label="Current password"
            name="current"
            required
          >
            <UInput
              v-model="passwordForm.current"
              type="password"
              autocomplete="current-password"
              class="w-full"
            />
          </UFormField>
          <UFormField
            label="New password"
            name="next"
            hint="At least 8 characters"
            required
          >
            <PasswordStrengthField
              id="settings-new-password"
              v-model="passwordForm.next"
              placeholder="At least 8 characters"
              autocomplete="new-password"
            />
          </UFormField>
          <UFormField
            label="Confirm new password"
            name="confirm"
            :error="passwordForm.confirm && passwordForm.confirm !== passwordForm.next ? 'The passwords do not match.' : undefined"
            required
          >
            <UInput
              v-model="passwordForm.confirm"
              type="password"
              autocomplete="new-password"
              class="w-full"
            />
          </UFormField>
          <UAlert
            v-if="formError"
            color="neutral"
            variant="subtle"
            icon="i-lucide-triangle-alert"
            :description="formError"
          />
          <UButton
            type="submit"
            label="Change password"
            color="neutral"
            block
            :loading="busy"
            :disabled="!passwordChangeReady(passwordForm)"
          />
        </UForm>
      </template>
    </UModal>

    <UModal
      v-model:open="isResetOpen"
      title="Reset progress"
      description="This removes all your leaderboard scores and saved boards. Your account, plan and today's runs stay."
    >
      <template #body>
        <UForm
          :state="resetForm"
          class="space-y-4"
          @submit="submitReset"
        >
          <UFormField
            label="Current password"
            name="password"
            required
          >
            <UInput
              v-model="resetForm.password"
              type="password"
              autocomplete="current-password"
              class="w-full"
            />
          </UFormField>
          <UAlert
            v-if="formError"
            color="neutral"
            variant="subtle"
            icon="i-lucide-triangle-alert"
            :description="formError"
          />
          <UButton
            type="submit"
            label="Reset progress"
            color="warning"
            block
            :loading="busy"
            :disabled="!resetForm.password"
          />
        </UForm>
      </template>
    </UModal>

    <UModal
      v-model:open="isDeleteOpen"
      title="Delete account"
      description="This removes your account, leaderboard scores, saved boards, sessions and any days left on your pass. It cannot be undone."
    >
      <template #body>
        <UForm
          :state="deleteForm"
          class="space-y-4"
          @submit="submitDelete"
        >
          <UFormField
            label="Current password"
            name="password"
            required
          >
            <UInput
              v-model="deleteForm.password"
              type="password"
              autocomplete="current-password"
              class="w-full"
            />
          </UFormField>
          <UFormField
            label="Type DELETE to confirm"
            name="confirm"
            required
          >
            <UInput
              v-model="deleteForm.confirm"
              autocomplete="off"
              class="w-full"
            />
          </UFormField>
          <UAlert
            v-if="formError"
            color="neutral"
            variant="subtle"
            icon="i-lucide-triangle-alert"
            :description="formError"
          />
          <UButton
            type="submit"
            label="Delete account"
            color="error"
            block
            :loading="busy"
            :disabled="!deleteConfirmed(deleteForm.confirm) || !deleteForm.password"
          />
        </UForm>
      </template>
    </UModal>
  </main>
</template>
