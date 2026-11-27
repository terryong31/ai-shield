// Load: an arrival-rate mix like real play: 70% reads, 20% session reads, 10% wave runs.
import { TREND_STATS, env, target, thresholds } from '../lib/config.js'
import { anonymous, gameRun, leaderboard, levels, progress, summaryFor } from '../lib/checks.js'

export const options = {
  scenarios: {
    players: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 20,
      maxVUs: 100,
      stages: [
        { target: Number(env('K6_LOAD_RATE', '30')), duration: env('K6_LOAD_RAMP', '1m') },
        { target: Number(env('K6_LOAD_RATE', '30')), duration: env('K6_LOAD_DURATION', '3m') },
        { target: 0, duration: '30s' }
      ]
    }
  },
  thresholds: thresholds('load'),
  summaryTrendStats: TREND_STATS
}

export function setup() {
  return { base: target() }
}

export default function ({ base }) {
  const roll = Math.random()
  if (roll < 0.7) {
    if (roll < 0.45) leaderboard(base, __ITER)
    else levels(base)
  } else if (roll < 0.9) {
    anonymous(base)
    progress(base)
  } else {
    gameRun(base, __ITER)
  }
}

export const handleSummary = summaryFor('load')
