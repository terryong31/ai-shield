// Stress: bursts on the rate-limited routes. 429 with Retry-After is expected; 5xx never is.
import http from 'k6/http'
import { TREND_STATS, env, target, thresholds } from '../lib/config.js'
import { anonymous, gameRun, health, login, summaryFor } from '../lib/checks.js'
import { testUser } from '../lib/boards.js'

http.setResponseCallback(http.expectedStatuses({ min: 200, max: 399 }, 401, 429))

export const options = {
  vus: Number(env('K6_STRESS_VUS', '20')),
  duration: env('K6_STRESS_DURATION', '1m'),
  thresholds: thresholds('stress'),
  summaryTrendStats: TREND_STATS
}

export function setup() {
  return { base: target() }
}

export default function ({ base }) {
  anonymous(base, [200, 429])
  gameRun(base, __ITER, [200, 429])
  login(base, testUser(__VU, __ITER), [401, 429])
  health(base)
}

export const handleSummary = summaryFor('stress')
