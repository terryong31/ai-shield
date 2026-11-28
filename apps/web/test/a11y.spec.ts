import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']
const ROUTES = ['/', '/plans', '/auth/login', '/auth/register', '/auth/recover']

async function stubGateway(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/auth/me') {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Not authenticated' })
      })
      return
    }
    if (url.pathname === '/api/v1/game/levels') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ levels: [], billing_enabled: false, self_upgrade_enabled: false })
      })
      return
    }
    if (url.pathname === '/api/v1/game/progress') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] })
      })
      return
    }
    if (url.pathname.startsWith('/api/v1/game/leaderboard')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ entries: [], my_rank: null })
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({})
    })
  })
}

async function assertNoA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(WCAG_TAGS)
    .analyze()
  const violations = results.violations.map(v => ({
    id: v.id,
    impact: v.impact,
    help: v.help,
    targets: v.nodes.map(n => n.target)
  }))
  expect(violations).toEqual([])
}

for (const route of ROUTES) {
  test(`[WEB-ACCESS-001] web client WCAG 2.2 AA audit passes on ${route} (dark mode)`, async ({ page }) => {
    await stubGateway(page)
    const response = await page.goto(route, { waitUntil: 'networkidle' })
    expect(response?.status()).toBe(200)
    await assertNoA11yViolations(page)
  })
}

for (const route of ['/', '/plans', '/auth/login']) {
  test(`[WEB-ACCESS-001] web client WCAG 2.2 AA light-mode audit passes on ${route}`, async ({ browser }) => {
    const context = await browser.newContext({ colorScheme: 'light' })
    await context.addInitScript(() => {
      window.localStorage.setItem('nuxt-color-mode', 'light')
    })
    const page = await context.newPage()
    try {
      await stubGateway(page)
      const response = await page.goto(route, { waitUntil: 'networkidle' })
      expect(response?.status()).toBe(200)
      await expect(page.locator('html')).toHaveClass(/light/)
      await assertNoA11yViolations(page)
    } finally {
      await context.close()
    }
  })
}

test('[WEB-ACCESS-001] web client mobile reflow (390px) passes WCAG 2.2 AA', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const page = await context.newPage()
  try {
    await stubGateway(page)
    for (const route of ['/', '/plans', '/auth/login']) {
      await page.goto(route, { waitUntil: 'networkidle' })
      const overflow = await page.evaluate(() => {
        return document.documentElement.scrollWidth - document.documentElement.clientWidth
      })
      expect(overflow).toBeLessThanOrEqual(0)
      await assertNoA11yViolations(page)
    }
  } finally {
    await context.close()
  }
})
