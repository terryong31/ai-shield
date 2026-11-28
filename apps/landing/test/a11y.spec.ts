import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']

const ROUTES = [
  '/',
  '/pricing',
  '/changelog',
  '/privacy',
  '/terms',
  '/refund',
  '/ms',
  '/ms/pricing',
  '/ms/changelog',
  '/ms/privacy',
  '/ms/terms',
  '/ms/refund'
]

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

async function assertNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => {
    return document.documentElement.scrollWidth - document.documentElement.clientWidth
  })
  expect(overflow).toBeLessThanOrEqual(0)
}

for (const route of ROUTES) {
  test(`[WEB-ACCESS-001] WCAG 2.2 AA and rendered-HTML audit passes on ${route} (dark mode)`, async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', err => pageErrors.push(err.message))

    const response = await page.goto(route, { waitUntil: 'networkidle' })
    expect(response?.status()).toBe(200)
    expect(pageErrors).toEqual([])

    const title = await page.title()
    expect(title.trim().length).toBeGreaterThan(0)

    const description = await page.locator('meta[name="description"]').getAttribute('content')
    expect((description ?? '').trim().length).toBeGreaterThan(0)

    const canonical = await page.locator('link[rel="canonical"]').getAttribute('href')
    const expectedCanonical = route === '/' ? 'https://ai-shield.my' : `https://ai-shield.my${route}`
    expect(canonical).toBe(expectedCanonical)

    const hreflangs = await page.locator('link[rel="alternate"][hreflang]').count()
    expect(hreflangs).toBeGreaterThan(0)

    await expect(page.locator('header').first()).toBeVisible()
    await expect(page.locator('main').first()).toBeVisible()
    await expect(page.locator('footer').first()).toBeVisible()
    await expect(page.locator('h1').first()).toBeVisible()

    await assertNoHorizontalOverflow(page)
    await assertNoA11yViolations(page)
  })
}

for (const route of ['/', '/pricing', '/changelog', '/privacy']) {
  test(`[WEB-ACCESS-001] WCAG 2.2 AA light-mode contrast audit passes on ${route}`, async ({ browser }) => {
    const context = await browser.newContext({ colorScheme: 'light' })
    await context.addInitScript(() => {
      window.localStorage.setItem('nuxt-color-mode', 'light')
    })
    const page = await context.newPage()
    try {
      const response = await page.goto(route, { waitUntil: 'networkidle' })
      expect(response?.status()).toBe(200)
      await expect(page.locator('html')).toHaveClass(/light/)
      await assertNoA11yViolations(page)
    } finally {
      await context.close()
    }
  })
}

test('[WEB-ACCESS-001] keyboard navigation works for skip links (EN/MS), language toggle, and animation pause', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' })

  await page.keyboard.press('Tab')
  const enSkipLink = page.getByRole('link', { name: 'Skip to content' })
  await expect(enSkipLink).toBeFocused()
  await expect(enSkipLink).toBeVisible()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main-content')).toBeFocused()

  const pauseBtn = page.getByRole('button', { name: 'Pause animation' })
  await pauseBtn.focus()
  await expect(pauseBtn).toBeFocused()
  await page.keyboard.press('Enter')
  const playBtn = page.getByRole('button', { name: 'Play animation' })
  await expect(playBtn).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('picture img')).toHaveAttribute('src', '/images/board.webp')

  const langBtn = page.getByRole('button', { name: 'Tukar ke Bahasa Melayu' })
  await langBtn.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/ms(?:#|$)/)
  await expect(page.locator('html')).toHaveAttribute('lang', 'ms-MY')

  await page.goto('/ms', { waitUntil: 'networkidle' })
  await page.keyboard.press('Tab')
  const msSkipLink = page.getByRole('link', { name: 'Langkau ke kandungan' })
  await expect(msSkipLink).toBeFocused()
  await expect(msSkipLink).toBeVisible()
})

test('[WEB-ACCESS-001] mobile reflow (390px and 320px) and mobile nav drawer pass WCAG 2.2 AA', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const page = await context.newPage()
  try {
    for (const route of ['/', '/pricing', '/privacy']) {
      await page.goto(route, { waitUntil: 'networkidle' })
      await assertNoHorizontalOverflow(page)
      await assertNoA11yViolations(page)
    }

    await page.goto('/', { waitUntil: 'networkidle' })
    const menuBtn = page.getByRole('button', { name: /open menu/i })
    await menuBtn.click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await assertNoA11yViolations(page)

    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toBeHidden()

    await page.setViewportSize({ width: 320, height: 568 })
    await page.goto('/', { waitUntil: 'networkidle' })
    await assertNoHorizontalOverflow(page)
  } finally {
    await context.close()
  }
})

test('[WEB-ACCESS-001] honors prefers-reduced-motion: reduce', async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: 'reduce' })
  const page = await context.newPage()
  try {
    await page.goto('/', { waitUntil: 'networkidle' })

    const animationName = await page.locator('.star-layer').first().evaluate((el) => {
      return window.getComputedStyle(el).animationName
    })
    expect(animationName).toBe('none')

    const playBtn = page.getByRole('button', { name: 'Play animation' })
    await expect(playBtn).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('picture img')).toHaveAttribute('src', '/images/board.webp')

    await assertNoA11yViolations(page)
  } finally {
    await context.close()
  }
})
