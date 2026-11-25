import { expect, test, type Page } from '@playwright/test'
import { dragTool, node, openLevel, waitForBoard } from './board'
import { account } from './env'

async function save(page: Page) {
  const saved = page.waitForResponse(r => r.url().includes('/api/v1/game/') && r.request().method() === 'PUT')
  await page.getByRole('button', { name: /^Save/ }).click()
  expect((await saved).ok()).toBe(true)
}

test('a signed-in player saves a board and sees it after a reload', async ({ page }) => {
  test.skip(!account.email || !account.password, 'E2E_EMAIL and E2E_PASSWORD are not set')

  await page.goto('/auth/login', { waitUntil: 'networkidle' })
  await page.locator('input[name="email"]').fill(account.email)
  await page.locator('input[name="password"]').fill(account.password)
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL(url => url.pathname !== '/auth/login')

  // Start empty, so a board from an earlier run cannot pass the test.
  await openLevel(page, 'easy-2')
  await page.getByRole('button', { name: 'Restart' }).click()
  await dragTool(page, 'text_cleanup')
  await save(page)
  await page.reload({ waitUntil: 'networkidle' })
  await waitForBoard(page)
  await expect(node(page, 'text_cleanup')).toBeVisible()

  await page.getByRole('button', { name: 'Restart' }).click()
  await save(page)
  await page.reload({ waitUntil: 'networkidle' })
  await waitForBoard(page)
  await expect(node(page, 'text_cleanup')).toHaveCount(0)
})
