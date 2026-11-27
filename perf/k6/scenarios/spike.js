// Spike: 0 to 120 readers at once on the leaderboard, across every board (spec 0057).
import { TREND_STATS, env, target, thresholds } from '../lib/config.js'
import { health, leaderboard, summaryFor } from '../lib/checks.js'

const duration = env('K6_SPIKE_DURATION', '30s')

export const options = {
  scenarios: {
    burst: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { target: 120, duration: '2s' },
        { target: 120, duration },
        { target: 0, duration: '2s' }
      ]
    }
  },
  thresholds: thresholds('spike'),
  summaryTrendStats: TREND_STATS
}

export function setup() {
  const base = target()
  health(base)
  return { base }
}

export default function ({ base }) {
  leaderboard(base, __ITER + __VU)
}

export const handleSummary = summaryFor('spike')
