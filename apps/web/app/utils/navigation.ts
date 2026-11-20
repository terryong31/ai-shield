/**
 * Whether the browser's previous history entry is a page of this app
 * (WEB-GAME-015). vue-router stores that page's path in `history.state.back`;
 * it is `null` on the first page of a visit or after a full reload from outside.
 */
export function hasInAppHistory(state: unknown): boolean {
  if (typeof state !== 'object' || state === null) return false
  const back = (state as { back?: unknown }).back
  return typeof back === 'string' && back.startsWith('/') && !back.startsWith('//')
}
