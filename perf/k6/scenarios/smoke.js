// Smoke: a few VUs touch every main route once per iteration (spec 0057).
import { sleep } from 'k6'
import { TREND_STATS, env, target, thresholds } from '../lib/config.js'
import { anonymous, gameRun, health, leaderboard, levels, progress, summaryFor } from '../lib/checks.js'

export const options = {
  vus: 2,
  duration: env('K6_SMOKE_DURATION', '20s'),
  thresholds: thresholds('smoke'),
  summaryTrendStats: TREND_STATS
}

export function setup() {
  return { base: target() }
}

export default function ({ base }) {
  health(base)
  levels(base)
  leaderboard(base, __ITER)
  anonymous(base)
  progress(base)
  gameRun(base, __ITER)
  sleep(0.5)
}

export const handleSummary = summaryFor('smoke')
