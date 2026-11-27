// Soak: steady moderate load for a long time to catch drift and leaks (spec 0057).
import { sleep } from 'k6'
import { TREND_STATS, env, target, thresholds } from '../lib/config.js'
import { gameRun, health, leaderboard, levels, summaryFor } from '../lib/checks.js'

export const options = {
  vus: Number(env('K6_SOAK_VUS', '10')),
  duration: env('K6_SOAK_DURATION', '10m'),
  thresholds: thresholds('soak'),
  summaryTrendStats: TREND_STATS
}

export function setup() {
  return { base: target() }
}

export default function ({ base }) {
  health(base)
  leaderboard(base, __ITER)
  levels(base)
  if (__ITER % 5 === 0) gameRun(base, __ITER)
  sleep(1)
}

export const handleSummary = summaryFor('soak')
