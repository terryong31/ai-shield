import type {
  DifficultyCategory,
  DifficultyLeaderboardEntry,
  LeaderboardRankResponse,
  PlayerSessionStatus
} from '~/types/api'

export const LEADERBOARD_POLL_INTERVAL_MS = 20_000
export const LEADERBOARD_STALE_AFTER_MS = 20_000

export function formatRankLabel(rank: number): string {
  if (rank < 1000) return `#${rank}`
  return `${Math.floor(rank / 1000)}K+`
}

export type OwnRowPlacement
  = | { kind: 'none' }
    | { kind: 'highlight', rank: number, highlightIndex: number }
    | { kind: 'pin', rank: number, rankLabel: string, playerName: string, totalScore: number }
    | { kind: 'pin-unranked', message: string }

export function ownRowPlacement(
  entries: DifficultyLeaderboardEntry[],
  me: LeaderboardRankResponse | null,
  session: Pick<PlayerSessionStatus, 'authenticated' | 'is_anonymous' | 'player_name'> | null
): OwnRowPlacement {
  if (!session || !session.authenticated || session.is_anonymous) {
    return { kind: 'none' }
  }
  if (!me || me.rank === null || me.total_score === null) {
    return {
      kind: 'pin-unranked',
      message: 'You\'re not ranked yet. Win a level to join the leaderboard.'
    }
  }
  if (me.rank <= entries.length && entries.length > 0) {
    return {
      kind: 'highlight',
      rank: me.rank,
      highlightIndex: me.rank - 1
    }
  }
  return {
    kind: 'pin',
    rank: me.rank,
    rankLabel: formatRankLabel(me.rank),
    playerName: session.player_name,
    totalScore: me.total_score
  }
}

export interface LeaderboardPollerDeps {
  getLeaderboard: (difficulty: DifficultyCategory) => Promise<DifficultyLeaderboardEntry[]>
  getMyRank: (difficulty: DifficultyCategory) => Promise<LeaderboardRankResponse>
  isSignedIn: () => boolean
  isHidden: () => boolean
  initialTab?: DifficultyCategory
  onEntries?: (difficulty: DifficultyCategory, rows: DifficultyLeaderboardEntry[]) => void
  onMyRank?: (difficulty: DifficultyCategory, rank: LeaderboardRankResponse) => void
  now?: () => number
}

export function createLeaderboardPoller(deps: LeaderboardPollerDeps) {
  let activeTab: DifficultyCategory = deps.initialTab ?? 'Easy'
  const lastFetchedAt = new Map<DifficultyCategory, number>()
  let timer: ReturnType<typeof setInterval> | null = null
  const now = deps.now ?? (() => Date.now())

  const isStale = (tab: DifficultyCategory): boolean => {
    const ts = lastFetchedAt.get(tab)
    if (ts === undefined) return true
    return now() - ts >= LEADERBOARD_STALE_AFTER_MS
  }

  const refreshActive = async (options?: { force?: boolean }) => {
    const tab = activeTab
    if (!options?.force && !isStale(tab)) return
    const rows = await deps.getLeaderboard(tab)
    lastFetchedAt.set(tab, now())
    deps.onEntries?.(tab, rows)
    if (deps.isSignedIn()) {
      const rank = await deps.getMyRank(tab)
      deps.onMyRank?.(tab, rank)
    }
  }

  const switchTab = async (tab: DifficultyCategory) => {
    activeTab = tab
    await refreshActive({ force: false })
  }

  const start = () => {
    if (timer) return
    timer = setInterval(() => {
      if (deps.isHidden()) return
      void refreshActive({ force: true })
    }, LEADERBOARD_POLL_INTERVAL_MS)
  }

  const stop = () => {
    if (!timer) return
    clearInterval(timer)
    timer = null
  }

  const onVisibilityChange = async () => {
    if (deps.isHidden()) return
    await refreshActive({ force: false })
  }

  return {
    get activeTab() {
      return activeTab
    },
    refreshActive,
    switchTab,
    onVisibilityChange,
    start,
    stop,
    markDirty: (tab?: DifficultyCategory) => {
      if (tab) {
        lastFetchedAt.delete(tab)
      } else {
        lastFetchedAt.clear()
      }
    }
  }
}
