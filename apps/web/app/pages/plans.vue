<script setup lang="ts">
import { planCards } from '~/utils/gameBoard'
import { buildPageSeo } from '~/utils/seo'

const runtimeConfig = useRuntimeConfig()
useSeoMeta(buildPageSeo({
  title: 'Plans',
  description: 'Compare Free and Paid plans for ai-shield. Unlock 300 daily wave runs, 1,000 daily tests, AI safety nodes, and the custom BYOK agent sandbox.',
  path: '/plans',
  siteUrl: runtimeConfig.public.siteUrl
}))

// Plan picker (WEB-GAME-014): upgrade buttons across the app link here.
const { session, loadingAuth, refreshSession, upgradeToPaid } = usePlayerAuth()
const { getLevels } = useShieldApi()
const goBack = useGoBack()
const selfUpgradeEnabled = ref(false)

const plans = computed(() => planCards(session.value, { selfUpgradeEnabled: selfUpgradeEnabled.value }).map((plan) => {
  if (plan.action !== 'upgrade' || !plan.button) return plan
  return {
    ...plan,
    button: {
      ...plan.button,
      loading: loadingAuth.value,
      onClick: async () => {
        await upgradeToPaid()
        if (session.value.tier === 'paid') await goBack('/')
      }
    }
  }
}))

onMounted(async () => {
  await Promise.all([
    refreshSession(),
    getLevels()
      .then((catalog) => {
        selfUpgradeEnabled.value = Boolean(catalog.self_upgrade_enabled)
      })
      .catch(() => {})
  ])
})
</script>

<template>
  <main class="h-full overflow-y-auto">
    <div class="mx-auto flex min-h-full w-full max-w-4xl flex-col justify-center gap-6 p-4">
      <div class="flex items-center gap-3">
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
          Plans
        </h1>
      </div>

      <UPricingPlans
        :plans="plans"
        scale
      />
    </div>
  </main>
</template>
