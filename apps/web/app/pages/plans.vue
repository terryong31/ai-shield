<script setup lang="ts">
import type { BillingSyncResponse, GameCatalogResponse } from '~/types/api'
import { errorDetail } from '~/utils/account'
import { isAllowedCheckoutUrl, waitForPass } from '~/utils/billing'
import { planCards } from '~/utils/gameBoard'
import { buildPageSeo } from '~/utils/seo'
import { withSsrTimeout } from '~/utils/ssr'

const runtimeConfig = useRuntimeConfig()
useSeoMeta(buildPageSeo({
  title: 'Plans',
  description: 'Compare Free and Paid plans for ai-shield. Unlock 50 daily wave runs, all 19 campaign levels, AI safety nodes, and the custom BYOK agent sandbox.',
  path: '/plans',
  siteUrl: runtimeConfig.public.siteUrl
}))

// Plan picker (WEB-GAME-014): upgrade buttons across the app link here.
const { session, isLoggedIn, loadingAuth, refreshSession, upgradeToPaid } = usePlayerAuth()
const { getLevels, startCheckout, syncBilling } = useShieldApi()
const route = useRoute()
const router = useRouter()
const toast = useToast()
const goBack = useGoBack()
interface BillingFlags {
  selfUpgradeEnabled: boolean
  billingEnabled: boolean
}

// Null until the gateway answers.
const billing = useState<BillingFlags | null>('shield_billing_flags', () => null)
const billingEnabled = computed(() => billing.value?.billingEnabled ?? false)
// The session hint has no pass end date, so a Paid player waits for the real session.
const sessionReady = ref(false)
const ready = ref(false)
const pending = computed(() =>
  (billing.value === null && !ready.value) || (session.value.tier === 'paid' && !sessionReady.value)
)

const loadBilling = async (request: Promise<GameCatalogResponse>) => {
  try {
    const catalog = await request
    billing.value = {
      selfUpgradeEnabled: Boolean(catalog.self_upgrade_enabled),
      billingEnabled: Boolean(catalog.billing_enabled)
    }
  } catch (err) {
    console.warn('Billing state unavailable:', (err as Error).message)
  }
}

onServerPrefetch(() => loadBilling(withSsrTimeout(getLevels())))
const redirecting = ref(false)

// Stripe-hosted checkout (spec 0049): only the webhook grants the pass.
const buyPass = async () => {
  redirecting.value = true
  try {
    const { url } = await startCheckout()
    // Leave the site only for Stripe's own checkout page (spec 0053).
    if (!isAllowedCheckoutUrl(url)) {
      throw new Error('Payments are unavailable. Try again later.')
    }
    await navigateTo(url, { external: true })
  } catch (err) {
    redirecting.value = false
    toast.add({
      title: 'Checkout unavailable',
      description: errorDetail(err, 'Payments are unavailable. Try again later.'),
      icon: 'i-lucide-triangle-alert',
      color: 'neutral'
    })
  }
}

// Reads the open checkout from Stripe, so a missed webhook or a lost connection is repaired here.
const syncState = ref<BillingSyncResponse['state']>('none')
const syncPass = async (cancel = false) => {
  if (!billingEnabled.value || !isLoggedIn.value) return
  try {
    const result = await syncBilling(cancel)
    syncState.value = result.state
    session.value = result.session
  } catch (err) {
    syncState.value = 'processing'
    console.warn('Checkout sync unavailable:', err)
  }
}

const confirmPass = async () => {
  if (!isLoggedIn.value) {
    toast.add({
      title: 'Sign in to see your pass',
      description: 'The pass belongs to the account that started the payment.',
      icon: 'i-lucide-log-in',
      color: 'neutral'
    })
    return
  }
  const paid = await waitForPass({
    refresh: () => syncPass(),
    isPaid: () => session.value.tier === 'paid' && (syncState.value === 'none' || syncState.value === 'paid')
  })
  toast.add(paid
    ? { title: 'Pass active', description: 'The Paid plan is ready.', icon: 'i-lucide-badge-check', color: 'neutral' }
    : {
        title: 'Payment is processing',
        description: 'Your pass starts when Stripe confirms the payment. You can close this page.',
        icon: 'i-lucide-clock',
        color: 'neutral'
      })
}

// The browser restores this page as it was when the player goes back from Stripe.
useEventListener('pageshow', () => {
  redirecting.value = false
})

const plans = computed(() => planCards(session.value, {
  selfUpgradeEnabled: billing.value?.selfUpgradeEnabled ?? false,
  billingEnabled: billingEnabled.value,
  pending: pending.value
}).map((plan) => {
  if (plan.action === 'checkout' && plan.button) {
    return { ...plan, button: { ...plan.button, loading: redirecting.value, onClick: buyPass } }
  }
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
  const checkout = route.query.checkout
  if (checkout !== undefined) await router.replace({ query: {} })
  await Promise.all([
    refreshSession().finally(() => {
      sessionReady.value = true
    }),
    loadBilling(getLevels())
  ])
  ready.value = true
  if (checkout === 'success') await confirmPass()
  else await syncPass(checkout === 'cancelled')
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

      <p class="text-center text-sm text-muted">
        Stripe takes the payment on its own page; we never see your card. See our
        <ULink
          to="/privacy"
          class="font-medium text-highlighted"
        >Privacy Policy</ULink>.
      </p>
    </div>
  </main>
</template>
