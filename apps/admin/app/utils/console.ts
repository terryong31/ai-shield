import type { ClearanceStatus, ScoreRecord } from '~/types/api'

export interface ConsoleScoreStats {
  scores: number
  players: number
  byLevel: { easy: number, medium: number, hard: number }
  medals: { gold: number, silver: number, bronze: number }
}

export function resolveConsoleAccess(status: ClearanceStatus): {
  allowed: boolean
  expiresAt: string | null
} {
  return {
    allowed: Boolean(status.granted),
    expiresAt: status.expires_at ?? null
  }
}

export function consoleScoreStats(records: ScoreRecord[]): ConsoleScoreStats {
  const players = new Set<string>()
  const byLevel = { easy: 0, medium: 0, hard: 0 }
  const medals = { gold: 0, silver: 0, bronze: 0 }

  for (const r of records) {
    players.add(r.player_name)
    if (r.level_id.startsWith('easy')) byLevel.easy += 1
    else if (r.level_id.startsWith('medium')) byLevel.medium += 1
    else if (r.level_id.startsWith('hard')) byLevel.hard += 1

    const medal = String(r.medal ?? '').toLowerCase()
    if (medal === 'gold') medals.gold += 1
    else if (medal === 'silver') medals.silver += 1
    else if (medal === 'bronze') medals.bronze += 1
  }

  return {
    scores: records.length,
    players: players.size,
    byLevel,
    medals
  }
}
