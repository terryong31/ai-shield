import { expect, test } from '@playwright/test'
import { connect, dragTool, openLevel } from './board'

// Easy levels run no agent model and Word filter is a free rule check: no paid call.
test('an anonymous player builds a board, runs a wave and sees a score', async ({ page }) => {
  await openLevel(page, 'easy-1')
  await dragTool(page, 'word_filter')
  await connect(page, 'incoming', 'word_filter')
  await connect(page, 'word_filter', 'assistant')

  const run = page.waitForResponse(r => r.url().endsWith('/api/v1/game/run'))
  await page.getByRole('button', { name: 'Run wave' }).click()
  const response = await run
  expect(response.status()).toBe(200)
  const { score } = await response.json()

  const results = page.getByRole('dialog', { name: 'Run results' })
  await expect(results).toBeVisible()
  await expect(results.getByText(score.total_score.toLocaleString('en-US'), { exact: true })).toBeVisible()
  await expect(results.getByText(/^\s*(Victory|Defeat)\s*$/)).toBeVisible()
})
