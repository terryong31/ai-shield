<script setup lang="ts">
import type { AuthFormField, FormSubmitEvent, NavigationMenuItem } from '@nuxt/ui'

const { granted, loginWithAuth, clearPassphrase } = usePassphrase()

const open = ref(false)
const signingIn = ref(false)

const close = () => {
  open.value = false
}

const authFields: AuthFormField[] = [
  {
    name: 'email',
    type: 'email',
    label: 'Email',
    placeholder: 'admin@ai-shield.local',
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

const onAuthSubmit = async (event: FormSubmitEvent<{ email?: string, password?: string }>) => {
  signingIn.value = true
  try {
    await loginWithAuth(event.data.email ?? '', event.data.password ?? '')
  } finally {
    signingIn.value = false
  }
}

const links = [[{
  label: 'Overview',
  icon: 'i-lucide-chart-no-axes-column',
  to: '/_console',
  exact: true,
  onSelect: close
}, {
  label: 'Audit logs',
  icon: 'i-lucide-scroll-text',
  to: '/_console/logs',
  onSelect: close
}, {
  label: 'Settings',
  icon: 'i-lucide-sliders-horizontal',
  to: '/_console/settings',
  onSelect: close
}], [{
  label: 'Main menu',
  icon: 'i-lucide-house',
  to: '/',
  onSelect: close
}]] satisfies NavigationMenuItem[][]
</script>

<template>
  <div
    v-if="!granted"
    class="flex h-dvh w-screen items-center justify-center bg-default p-6"
  >
    <UCard
      variant="outline"
      class="w-full max-w-sm"
    >
      <UAuthForm
        title="Login"
        icon="i-lucide-lock"
        :fields="authFields"
        :loading="signingIn"
        :submit="{ label: 'Sign in', color: 'neutral', variant: 'solid', block: true }"
        @submit="onAuthSubmit"
      />
    </UCard>
  </div>

  <UDashboardGroup
    v-else
    unit="rem"
  >
    <UDashboardSidebar
      id="shield-console"
      v-model:open="open"
      collapsible
      resizable
      class="bg-elevated/25"
      :ui="{ footer: 'lg:border-t lg:border-default' }"
    >
      <template #header="{ collapsed }">
        <NuxtLink
          to="/_console"
          class="flex items-center gap-2 min-w-0"
        >
          <UIcon
            name="i-lucide-terminal"
            class="size-5 shrink-0 text-highlighted"
          />
          <span
            v-if="!collapsed"
            class="text-sm font-bold tracking-tight text-highlighted truncate"
          >
            ai-shield
          </span>
        </NuxtLink>
      </template>

      <template #default="{ collapsed }">
        <UNavigationMenu
          :collapsed="collapsed"
          :items="links[0]"
          orientation="vertical"
          tooltip
          popover
        />

        <UNavigationMenu
          :collapsed="collapsed"
          :items="links[1]"
          orientation="vertical"
          tooltip
          class="mt-auto"
        />
      </template>

      <template #footer="{ collapsed }">
        <UButton
          icon="i-lucide-log-out"
          :label="collapsed ? undefined : 'Sign out'"
          color="neutral"
          variant="ghost"
          :square="collapsed"
          :block="!collapsed"
          :ui="{ base: !collapsed ? 'justify-start' : undefined }"
          aria-label="Sign out"
          @click="clearPassphrase"
        />
      </template>
    </UDashboardSidebar>

    <slot />
  </UDashboardGroup>
</template>
