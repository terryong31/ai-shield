import { describe, expect, it } from 'vitest'
import { consoleScoreStats, resolveConsoleAccess } from '../app/utils/console'

describe('Admin console helpers (spec 0059)', () => {
  it('[WEB-ADMIN-002] resolves console access and computes score statistics', () => {
    expect(resolveConsoleAccess({ granted: false, expires_at: null })).toEqual({
      allowed: false,
      expiresAt: null
    })
    expect(resolveConsoleAccess({ granted: true, expires_at: '2026-12-01T00:00:00Z' })).toEqual({
      allowed: true,
      expiresAt: '2026-12-01T00:00:00Z'
    })

    const stats = consoleScoreStats([
      {
        id: '1',
        player_name: 'Ada',
        level_id: 'easy-1',
        total_score: 9000,
        medal: 'gold',
        won: true,
        mastered: true,
        attacks_blocked: 10,
        attacks_total: 10,
        false_alarms: 0,
        avg_latency_ms: 2.5,
        total_cost_usd: 0,
        created_at: '2026-11-28T00:00:00Z'
      }
    ])
    expect(stats.scores).toBe(1)
    expect(stats.players).toBe(1)
    expect(stats.byLevel.easy).toBe(1)
    expect(stats.medals.gold).toBe(1)
  })
})
