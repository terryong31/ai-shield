<script setup lang="ts">
import type { AuthFormField, FormSubmitEvent, NavigationMenuItem } from '@nuxt/ui'

const runtimeConfig = useRuntimeConfig()
const { granted, loadAccess, signIn, signOut } = useAdminAccess()

onMounted(loadAccess)

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
    placeholder: 'admin@ai-shield.my',
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
    await signIn(event.data.email ?? '', event.data.password ?? '')
  } finally {
    signingIn.value = false
  }
}

const webUrl = computed(() => String(runtimeConfig.public.webUrl || 'https://play.ai-shield.my'))

const links = computed<NavigationMenuItem[][]>(() => [[{
  label: 'Overview',
  icon: 'i-lucide-chart-no-axes-column',
  to: '/',
  exact: true,
  onSelect: close
}, {
  label: 'Settings',
  icon: 'i-lucide-sliders-horizontal',
  to: '/settings',
  onSelect: close
}], [{
  label: 'Open game',
  icon: 'i-lucide-external-link',
  to: webUrl.value,
  target: '_blank',
  external: true,
  onSelect: close
}]])
</script>

<template>
  <main
    v-if="!granted"
    class="flex min-h-dvh w-full items-center justify-center bg-default p-6"
  >
    <UCard
      variant="outline"
      class="w-full max-w-sm"
    >
      <UAuthForm
        title="Admin Login"
        icon="i-lucide-lock"
        :fields="authFields"
        :loading="signingIn"
        :submit="{ label: 'Sign in', color: 'neutral', variant: 'solid', block: true }"
        @submit="onAuthSubmit"
      />
    </UCard>
  </main>

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
          to="/"
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
            ai-shield Admin
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
          @click="signOut"
        />
      </template>
    </UDashboardSidebar>

    <slot />
  </UDashboardGroup>
</template>
