import { injectAnalytics } from '@vercel/analytics/nuxt/runtime'
import { injectSpeedInsights } from '@vercel/speed-insights/nuxt/runtime'
import { scrubAnalyticsEvent } from '~/utils/analytics'

// Vercel Web Analytics and Speed Insights report only on Vercel deployments. Every
// event goes through the scrubber, so auth links never reach them (spec 0053).
export default defineNuxtPlugin(() => {
  injectAnalytics({ beforeSend: scrubAnalyticsEvent })
  injectSpeedInsights({ beforeSend: scrubAnalyticsEvent })
})
