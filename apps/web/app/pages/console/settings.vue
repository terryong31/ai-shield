<script setup lang="ts">
import { resolveConsoleAccess } from '~/utils/gameBoard'

definePageMeta({
  path: '/_console/settings',
  layout: 'dashboard'
})

const { status, granted, clearPassphrase } = usePassphrase()
const access = computed(() => resolveConsoleAccess(status.value))
</script>

<template>
  <UDashboardPanel id="console-settings">
    <template #header>
      <UDashboardNavbar title="Settings">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div
        v-if="!access.allowed"
        class="py-16"
      >
        <UEmpty
          icon="i-lucide-lock"
          title="Admin access required"
          description="Sign in to view settings."
        />
      </div>

      <div
        v-else
        class="space-y-6"
      >
        <UPageCard
          title="Appearance"
          variant="outline"
        >
          <UFormField
            name="theme"
            label="Theme"
            description="Dark or light mode"
            orientation="horizontal"
            class="flex items-center justify-between gap-4"
          >
            <UColorModeSwitch color="neutral" />
          </UFormField>
        </UPageCard>

        <UPageCard
          title="Session"
          variant="outline"
        >
          <div class="flex items-center justify-between">
            <span class="text-sm text-muted">
              Status: {{ granted ? 'Active' : 'Locked' }}
            </span>
            <UButton
              v-if="granted"
              label="Sign out"
              color="error"
              variant="outline"
              size="sm"
              @click="clearPassphrase"
            />
          </div>
        </UPageCard>
      </div>
    </template>
  </UDashboardPanel>
</template>
