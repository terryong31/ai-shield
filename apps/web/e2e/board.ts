import { expect, type Page } from '@playwright/test'

export const tool = (page: Page, kind: string) => page.locator(`[data-tour="tool-${kind}"]`)
export const node = (page: Page, kind: string) => page.locator(`.vue-flow [data-tour="node-${kind}"]`)

/** Opens a level with its guided tour already seen, after the board has loaded. */
export async function openLevel(page: Page, levelId: string) {
  await page.addInitScript(
    id => localStorage.setItem(`ai-shield:tour-seen:${id}`, '1'),
    levelId
  )
  await page.goto(`/game?level=${levelId}`, { waitUntil: 'networkidle' })
  await waitForBoard(page)
}

export async function waitForBoard(page: Page) {
  await expect(node(page, 'assistant')).toBeVisible()
  await expect(page.getByText('Loading workflow...')).toBeHidden()
}

/** Drags a tool onto an empty part of the canvas, as a player does. */
export async function dragTool(page: Page, kind: string) {
  await tool(page, kind).dragTo(page.locator('[data-tour="canvas"]'), {
    targetPosition: { x: 400, y: 560 }
  })
  await expect(node(page, kind)).toBeVisible()
}

/** Draws a wire from one node's output dot to another node's input dot. */
export async function connect(page: Page, from: string, to: string) {
  const edges = page.locator('.vue-flow__edge')
  const before = await edges.count()
  const source = await node(page, from).locator('.vue-flow__handle.source span').first().boundingBox()
  const target = await node(page, to).locator('.vue-flow__handle.target span').boundingBox()
  if (!source || !target) throw new Error(`No ports to connect ${from} to ${to}`)
  await page.mouse.move(source.x + source.width / 2, source.y + source.height / 2)
  await page.mouse.down()
  await page.mouse.move(target.x + target.width / 2, target.y + target.height / 2, { steps: 12 })
  await page.mouse.up()
  await expect(edges).toHaveCount(before + 1)
}
