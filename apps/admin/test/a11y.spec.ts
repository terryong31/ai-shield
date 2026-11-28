import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']

async function stubClearance(page: Page, granted: boolean) {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/clearance') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          granted,
          expires_at: granted ? '2026-11-28T23:59:59Z' : null
        })
      })
      return
    }
    if (url.pathname.startsWith('/api/v1/game/scores')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([])
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

for (const granted of [false, true]) {
  for (const route of ['/', '/settings']) {
    test(`[WEB-ACCESS-001] admin WCAG 2.2 AA audit passes on ${route} (granted=${String(granted)}, dark mode)`, async ({ page }) => {
      await stubClearance(page, granted)
      const response = await page.goto(route, { waitUntil: 'networkidle' })
      expect(response?.status()).toBe(200)
      await assertNoA11yViolations(page)
    })
  }
}

test('[WEB-ACCESS-001] admin WCAG 2.2 AA light-mode and mobile reflow audit passes', async ({ browser }) => {
  const context = await browser.newContext({
    colorScheme: 'light',
    viewport: { width: 390, height: 844 }
  })
  await context.addInitScript(() => {
    window.localStorage.setItem('nuxt-color-mode', 'light')
  })
  const page = await context.newPage()
  try {
    await stubClearance(page, true)
    for (const route of ['/', '/settings']) {
      await page.goto(route, { waitUntil: 'networkidle' })
      await expect(page.locator('html')).toHaveClass(/light/)
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
