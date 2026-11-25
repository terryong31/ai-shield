import { expect, test } from '@playwright/test'

test('the main menu shows the leaderboard and leads to the levels', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' })
  await expect(page.getByRole('heading', { name: 'ai-shield' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Leaderboard' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Player' })).toBeVisible()

  await page.getByRole('button', { name: 'Play Game' }).click()
  await page.getByRole('button', { name: /^Easy.*levels/ }).click()
  await expect(page.getByRole('button', { name: /Public Helpdesk/ })).toBeVisible()
})

test('the gateway answers through the web proxy', async ({ request }) => {
  const health = await request.get('/api/v1/health')
  expect(health.status()).toBe(200)
  expect(await health.json()).toMatchObject({ status: 'healthy' })

  // The page has built-in levels, so only the route shows that the catalog works.
  const levels = await request.get('/api/v1/game/levels')
  expect(levels.status()).toBe(200)
  expect((await levels.json()).levels.length).toBeGreaterThan(0)
})
