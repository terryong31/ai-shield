import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { planCards } from '../app/utils/gameBoard'
import * as billing from '../app/utils/billing'
import { DEFAULT_ANONYMOUS_SESSION } from '../app/utils/sessionHint'

const read = (...parts: string[]) => readFileSync(join(import.meta.dirname, '..', 'app', ...parts), 'utf-8')
const FREE = {
  ...DEFAULT_ANONYMOUS_SESSION,
  authenticated: true,
  is_anonymous: false,
  tier: 'free' as const,
  player_name: 'Ada'
}
const PASS = { ...FREE, tier: 'paid' as const, paid_until: '2026-12-25T10:00:00Z' }

describe('Stripe pass checkout (spec 0049)', () => {
  it('[WEB-BILL-001] sells a 30-day pass that redirects to Stripe, or shows Coming soon', () => {
    const paid = planCards(FREE, { billingEnabled: true, selfUpgradeEnabled: false })[1]!
    expect([paid.price, paid.billingCycle]).toEqual(['$5', '/30 days'])
    expect(paid.terms).toBeUndefined()
    expect(paid.features).toContain('One payment, does not renew')
    expect(planCards(FREE, { billingEnabled: true })[0]!.billingCycle).toBeUndefined()
    expect(paid.button?.label).toBe('Buy 30-day pass')
    expect(paid.action).toBe('checkout')

    const off = planCards(FREE, { billingEnabled: false, selfUpgradeEnabled: false })[1]!
    expect(off.button).toMatchObject({ label: 'Coming soon', disabled: true })

    expect(read('composables', 'useShieldApi.ts')).toContain('\'/billing/checkout\', { method: \'POST\' }')
    const page = read('pages', 'plans.vue')
    expect(page).toMatch(/const \{ url \} = await startCheckout\(\)/)
    expect(page).toMatch(/navigateTo\(url, \{ external: true \}\)/)
  })

  it('[WEB-BILL-002] waits at most 20 seconds for the pass and reports success only when paid', async () => {
    let clock = 0
    const sleep = async (ms: number) => {
      clock += ms
    }
    let calls = 0
    const ok = await billing.waitForPass({
      refresh: async () => {
        calls += 1
      },
      isPaid: () => calls >= 3,
      sleep,
      now: () => clock
    })
    expect(ok).toBe(true)
    expect(calls).toBe(3)

    clock = 0
    const never = await billing.waitForPass({ refresh: async () => {}, isPaid: () => false, sleep, now: () => clock })
    expect(never).toBe(false)
    expect(clock).toBeLessThanOrEqual(20_000)

    const page = read('pages', 'plans.vue')
    expect(page).toMatch(/route\.query\.checkout/)
    expect(page).toMatch(/router\.replace\(\{ query: \{\} \}\)/)
    expect(page).toMatch(/=== 'success'/)
  })

  it('[WEB-BILL-003] shows the end date and an Extend button for an active pass', () => {
    const paid = planCards(PASS, { billingEnabled: true, selfUpgradeEnabled: false })[1]!
    expect(paid.button?.label).toBe('Extend')
    expect(paid.action).toBe('checkout')
    expect(paid.description).toContain(billing.formatPassEnd('2026-12-25T10:00:00Z'))

    const granted = planCards({ ...PASS, paid_until: null }, { billingEnabled: true, selfUpgradeEnabled: false })[1]!
    expect(granted.button).toMatchObject({ label: 'Current plan', disabled: true })
  })

  it('[WEB-BILL-004] cancels the open session on return and syncs on each visit', () => {
    expect(read('composables', 'useShieldApi.ts')).toMatch(/syncBilling: \(cancel = false\)[\s\S]*?'\/billing\/sync', \{ method: 'POST', body: \{ cancel \} \}/)
    const page = read('pages', 'plans.vue')
    expect(page).toMatch(/syncPass\(checkout === 'cancelled'\)/)
    expect(page).toMatch(/if \(!billingEnabled\.value \|\| !isLoggedIn\.value\) return/)
  })

  it('[WEB-BILL-005] resets the button after the back button and asks a signed-out player to sign in', () => {
    const page = read('pages', 'plans.vue')
    expect(page).toMatch(/useEventListener\('pageshow'[\s\S]*?redirecting\.value = false/)
    expect(page).toMatch(/Sign in to see your pass/)
  })
})
