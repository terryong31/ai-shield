export const SITE_NAME = 'ai-shield'
export const SITE_URL_DEFAULT = 'http://localhost:3000'
export const TWITTER_CARD_PATH = '/twitter-card.png'
export const TWITTER_CARD_ALT = 'ai-shield defence board with wired checks that block prompt injections'
export const DEFAULT_DESCRIPTION = 'Wire layered security checks on an interactive node board to protect AI agents from prompt injection waves, jailbreaks, secret leaks, and tool hijacking.'

export interface PageSeoInput {
  title: string
  description: string
  path?: string
  siteUrl?: string
  noindex?: boolean
}

export function resolveSiteUrl(siteUrl?: string): string {
  const trimmed = (siteUrl || SITE_URL_DEFAULT).trim().replace(/\/+$/, '')
  return trimmed || SITE_URL_DEFAULT
}

export function buildPageSeo(input: PageSeoInput) {
  const base = resolveSiteUrl(input.siteUrl)
  const normalizedPath = input.path
    ? (input.path.startsWith('/') ? input.path : `/${input.path}`)
    : '/'
  const fullTitle = input.title.includes(SITE_NAME)
    ? input.title
    : `${input.title} | ${SITE_NAME}`
  const imageUrl = `${base}${TWITTER_CARD_PATH}`
  const imageAlt = TWITTER_CARD_ALT

  return {
    title: input.title,
    description: input.description,
    ogTitle: fullTitle,
    ogDescription: input.description,
    ogType: 'website' as const,
    ogSiteName: SITE_NAME,
    ogUrl: `${base}${normalizedPath}`,
    ogImage: imageUrl,
    ogImageAlt: imageAlt,
    ogImageWidth: 1200,
    ogImageHeight: 630,
    twitterCard: 'summary_large_image' as const,
    twitterTitle: fullTitle,
    twitterDescription: input.description,
    twitterImage: imageUrl,
    twitterImageAlt: imageAlt,
    robots: input.noindex ? 'noindex, nofollow' : 'index, follow'
  }
}

export function buildGameJsonLd(siteUrl?: string) {
  const base = resolveSiteUrl(siteUrl)
  return {
    '@context': 'https://schema.org',
    '@type': 'VideoGame',
    'name': SITE_NAME,
    'description': DEFAULT_DESCRIPTION,
    'url': `${base}/`,
    'image': `${base}${TWITTER_CARD_PATH}`,
    'applicationCategory': 'GameApplication',
    'genre': ['Security Simulation', 'Puzzle', 'Strategy'],
    'operatingSystem': 'Web Browser',
    'inLanguage': 'en',
    'offers': {
      '@type': 'Offer',
      'price': '0',
      'priceCurrency': 'USD',
      'availability': 'https://schema.org/InStock'
    }
  }
}

/** JSON for a `<script type="application/ld+json">` that no value can close (spec 0053). */
export function serializeJsonLd(value: unknown): string {
  return JSON.stringify(value).replace(/</g, '\\u003c')
}
