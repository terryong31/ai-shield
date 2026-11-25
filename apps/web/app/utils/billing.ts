/** Pure rules for the Stripe pass (spec 0049). */
const PASS_WAIT_MS = 20_000
const PASS_POLL_MS = 2_000

export interface PassWait {
  refresh: () => Promise<void>
  isPaid: () => boolean
  sleep?: (ms: number) => Promise<void>
  now?: () => number
}

/** The webhook grants the pass, so it can arrive a little after the player returns. */
export async function waitForPass({
  refresh,
  isPaid,
  sleep = ms => new Promise(resolve => setTimeout(resolve, ms)),
  now = Date.now
}: PassWait): Promise<boolean> {
  const deadline = now() + PASS_WAIT_MS
  while (true) {
    await refresh()
    if (isPaid()) return true
    if (now() + PASS_POLL_MS > deadline) return false
    await sleep(PASS_POLL_MS)
  }
}

export function formatPassEnd(paidUntil: string): string {
  return new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(paidUntil))
}
