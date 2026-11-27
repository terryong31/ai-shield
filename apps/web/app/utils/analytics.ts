/**
 * Analytics events never carry the query of an auth page (spec 0053): those links
 * hold one-time codes and tokens.
 */
export function scrubAnalyticsEvent<T extends { url: string }>(event: T): T | null {
  let url: URL
  try {
    url = new URL(event.url)
  } catch {
    return null
  }
  if (!url.pathname.startsWith('/auth/')) return event
  url.search = ''
  url.hash = ''
  return { ...event, url: url.toString() }
}
