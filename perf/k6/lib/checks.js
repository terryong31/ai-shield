// Checks, custom metrics and the redacted summary (spec 0057).
import http from 'k6/http'
import { check } from 'k6'
import { Counter, Trend } from 'k6/metrics'
import { BOARDS } from './boards.js'
import { env, requestHeaders } from './config.js'

export const leaderboardDuration = new Trend('shield_leaderboard_duration', true)
export const waveRunDuration = new Trend('shield_wave_run_duration', true)
export const unexpected5xx = new Counter('shield_unexpected_5xx')
export const rateLimited = new Counter('shield_rate_limited')

const DIFFICULTIES = ['Easy', 'Medium', 'Hard', '']
// Serialized once per VU, not once per request.
const BOARD_BODIES = BOARDS.map(board => JSON.stringify(board))

function record(res, name, expected) {
  if (res.status >= 500 || res.status === 0) unexpected5xx.add(1)
  if (res.status === 429) {
    rateLimited.add(1)
    return check(res, { [`${name} 429 has Retry-After`]: r => Boolean(r.headers['Retry-After']) })
  }
  return check(res, { [`${name} ${expected.join('/')}`]: r => expected.includes(r.status) })
}

function params(endpoint, kind) {
  return { headers: requestHeaders(), tags: { endpoint, kind } }
}

export function health(base) {
  return record(http.get(`${base}/api/v1/health`, params('health', 'read')), 'health', [200])
}

export function levels(base) {
  return record(http.get(`${base}/api/v1/game/levels`, params('levels', 'read')), 'levels', [200])
}

export function leaderboard(base, iteration = 0) {
  const difficulty = DIFFICULTIES[iteration % DIFFICULTIES.length]
  const query = difficulty ? `?difficulty=${difficulty}` : ''
  const res = http.get(`${base}/api/v1/game/leaderboard${query}`, params('leaderboard', 'read'))
  leaderboardDuration.add(res.timings.duration)
  return record(res, 'leaderboard', [200])
}

export function anonymous(base, expected = [200]) {
  const res = http.post(`${base}/api/v1/auth/anonymous`, null, params('anonymous', 'write'))
  return record(res, 'anonymous', expected)
}

export function progress(base) {
  return record(http.get(`${base}/api/v1/game/progress`, params('progress', 'read')), 'progress', [200])
}

export function gameRun(base, iteration = 0, expected = [200]) {
  const body = BOARD_BODIES[iteration % BOARD_BODIES.length]
  const res = http.post(`${base}/api/v1/game/run`, body, params('game_run', 'write'))
  waveRunDuration.add(res.timings.duration)
  return record(res, 'game_run', expected)
}

export function login(base, user, expected) {
  const res = http.post(`${base}/api/v1/auth/login`, JSON.stringify(user), params('login', 'write'))
  return record(res, 'login', expected)
}

function trend(data, name) {
  const metric = data.metrics[name]
  if (!metric) return null
  const v = metric.values
  return { avg: v.avg, p95: v['p(95)'], p99: v['p(99)'], max: v.max }
}

function count(data, name) {
  return data.metrics[name] ? data.metrics[name].values.count : 0
}

function checksOf(group, out = {}) {
  for (const c of group.checks || []) out[c.name] = { passes: c.passes, fails: c.fails }
  for (const g of group.groups || []) checksOf(g, out)
  return out
}

/**
 * Only aggregate numbers and check names leave the run: no request, header, cookie or
 * token is ever copied into the report.
 */
export function summaryFor(profile) {
  return (data) => {
    const thresholdsOk = Object.values(data.metrics).every(
      m => !m.thresholds || Object.values(m.thresholds).every(t => t.ok)
    )
    const report = {
      profile,
      thresholds_ok: thresholdsOk,
      checks: checksOf(data.root_group),
      metrics: {
        http_reqs: count(data, 'http_reqs'),
        http_req_failed: data.metrics.http_req_failed ? data.metrics.http_req_failed.values.rate : 0,
        health: trend(data, 'http_req_duration{endpoint:health}'),
        leaderboard: trend(data, 'http_req_duration{endpoint:leaderboard}'),
        game_run: trend(data, 'http_req_duration{endpoint:game_run}'),
        unexpected_5xx: count(data, 'shield_unexpected_5xx'),
        rate_limited: count(data, 'shield_rate_limited')
      }
    }
    const text = `${profile}: ${report.metrics.http_reqs} requests, thresholds ${thresholdsOk ? 'passed' : 'FAILED'}, `
      + `unexpected 5xx ${report.metrics.unexpected_5xx}, rate limited ${report.metrics.rate_limited}\n`
    const dir = env('K6_REPORT_DIR', 'perf/k6/.reports')
    return { stdout: text, [`${dir}/${profile}-summary.json`]: JSON.stringify(report, null, 2) }
  }
}
