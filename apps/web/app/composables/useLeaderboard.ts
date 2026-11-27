import type {
  DifficultyCategory,
  DifficultyLeaderboardEntry,
  LeaderboardRankResponse,
  LevelId
} from '~/types/api'
import {
  LEADERBOARD_POLL_INTERVAL_MS,
  LEADERBOARD_STALE_AFTER_MS
} from '~/utils/leaderboard'
import { withSsrTimeout } from '~/utils/ssr'

const CACHE_KEY = 'shield_leaderboard_cache_v6'
const DIFFICULTIES: readonly DifficultyCategory[] = ['Easy', 'Medium', 'Hard']

type DifficultyFlags = Partial<Record<DifficultyCategory, boolean>>

// Keyed by difficulty: a request for one tab must never stand in for another.
const inFlightRefresh = new Map<DifficultyCategory, Promise<void>>()
let cacheHydrated = false
let pollTimer: ReturnType<typeof setInterval> | null = null
let visibilityListenerAttached = false
let subscribers = 0

export const useMyRanks = () =>
  useState<Partial<Record<DifficultyCategory, LeaderboardRankResponse>>>(
    'shield_leaderboard_my_ranks',
    () => ({})
  )

export const useLeaderboard = () => {
  const { getLeaderboard, getMyLeaderboardRank } = useShieldApi()
  const { isLoggedIn } = usePlayerAuth()

  const difficultyLeaderboards = useState<Record<DifficultyCategory, DifficultyLeaderboardEntry[]>>(
    'shield_difficulty_leaderboards',
    () => ({
      Easy: [],
      Medium: [],
      Hard: []
    })
  )
  const myRanks = useMyRanks()
  const lastFetchedAt = useState<Partial<Record<DifficultyCategory, number>>>(
    'shield_leaderboard_fetched_at',
    () => ({})
  )
  const loadedBy = useState<DifficultyFlags>('shield_leaderboard_loaded_by_difficulty', () => ({}))
  const loadingBy = useState<DifficultyFlags>('shield_leaderboard_loading_by_difficulty', () => ({}))
  const selectedTab = useState<LevelId>('shield_leaderboard_tab', () => 'easy-1')
  const selectedDifficulty = useState<DifficultyCategory>('shield_leaderboard_difficulty', () => 'Easy')
  // Both follow the visible tab, so switching to an unfetched difficulty shows its own loading state.
  const hasLoaded = computed(() => loadedBy.value[selectedDifficulty.value] === true)
  const loading = computed(() => loadingBy.value[selectedDifficulty.value] === true)

  const setFlag = (flags: Ref<DifficultyFlags>, diff: DifficultyCategory, value: boolean) => {
    flags.value = { ...flags.value, [diff]: value }
  }

  const hydrateFromCache = () => {
    if (!import.meta.client || cacheHydrated) return
    cacheHydrated = true
    try {
      const raw = window.sessionStorage.getItem(CACHE_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw) as Partial<Record<DifficultyCategory, DifficultyLeaderboardEntry[]>>
      for (const diff of DIFFICULTIES) {
        const rows = parsed[diff]
        if (!Array.isArray(rows) || loadedBy.value[diff]) continue
        difficultyLeaderboards.value = { ...difficultyLeaderboards.value, [diff]: rows }
        setFlag(loadedBy, diff, true)
      }
    } catch {
      // Ignore corrupt or unavailable sessionStorage.
    }
  }

  const persistToCache = () => {
    if (!import.meta.client) return
    try {
      // Only difficulties that were fetched: an unfetched empty list would read as "No scores yet".
      const fetched = Object.fromEntries(
        DIFFICULTIES.filter(diff => loadedBy.value[diff]).map(diff => [diff, difficultyLeaderboards.value[diff]])
      )
      window.sessionStorage.setItem(CACHE_KEY, JSON.stringify(fetched))
    } catch {
      // Ignore quota or storage errors.
    }
  }

  const isStale = (diff: DifficultyCategory): boolean => {
    const ts = lastFetchedAt.value[diff]
    if (ts === undefined) return true
    return Date.now() - ts >= LEADERBOARD_STALE_AFTER_MS
  }

  const refreshMyRank = async (diff: DifficultyCategory) => {
    if (!isLoggedIn.value) return
    try {
      const rank = await getMyLeaderboardRank(diff)
      myRanks.value = { ...myRanks.value, [diff]: rank }
    } catch {
      // Non-fatal: keep existing rank summary on transient errors.
    }
  }

  const refreshScores = async (options?: { background?: boolean, force?: boolean }) => {
    hydrateFromCache()
    const activeDiff = selectedDifficulty.value
    const force = options?.force ?? options?.background ?? false
    if (!force && !isStale(activeDiff)) {
      return
    }
    const pending = inFlightRefresh.get(activeDiff)
    if (pending) return pending

    if (!loadedBy.value[activeDiff]) {
      setFlag(loadingBy, activeDiff, true)
    }

    const request = (async () => {
      try {
        const [activeRows] = await Promise.all([
          getLeaderboard(activeDiff, 25),
          refreshMyRank(activeDiff)
        ])
        difficultyLeaderboards.value = {
          ...difficultyLeaderboards.value,
          [activeDiff]: activeRows
        }
        lastFetchedAt.value = {
          ...lastFetchedAt.value,
          [activeDiff]: Date.now()
        }
        setFlag(loadedBy, activeDiff, true)
        persistToCache()
      } catch (err) {
        console.warn('Scoreboard unavailable:', err)
      } finally {
        setFlag(loadingBy, activeDiff, false)
        inFlightRefresh.delete(activeDiff)
      }
    })()

    inFlightRefresh.set(activeDiff, request)
    return request
  }

  // Server render only: a slow gateway must not delay the page, the browser retries on mount.
  const prefetchScores = async () => {
    const diff = selectedDifficulty.value
    try {
      const rows = await withSsrTimeout(getLeaderboard(diff, 25))
      difficultyLeaderboards.value = { ...difficultyLeaderboards.value, [diff]: rows }
      lastFetchedAt.value = { ...lastFetchedAt.value, [diff]: Date.now() }
      setFlag(loadedBy, diff, true)
    } catch (err) {
      console.warn('Scoreboard prefetch skipped:', (err as Error).message)
    }
  }

  const handleVisibilityChange = () => {
    if (!import.meta.client || document.hidden) return
    if (isStale(selectedDifficulty.value)) {
      void refreshScores({ background: true, force: true })
    }
  }

  const startPolling = () => {
    if (!import.meta.client) return
    subscribers += 1
    if (!visibilityListenerAttached && typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibilityChange)
      visibilityListenerAttached = true
    }
    if (!pollTimer) {
      pollTimer = setInterval(() => {
        if (typeof document !== 'undefined' && document.hidden) return
        void refreshScores({ background: true, force: true })
      }, LEADERBOARD_POLL_INTERVAL_MS)
    }
  }

  const stopPolling = () => {
    subscribers = Math.max(0, subscribers - 1)
    if (subscribers > 0) return
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    if (visibilityListenerAttached && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      visibilityListenerAttached = false
    }
  }

  watch(selectedDifficulty, (diff) => {
    if (!import.meta.client) return
    if (isStale(diff)) {
      void refreshScores({ background: hasLoaded.value, force: true })
    } else if (isLoggedIn.value && myRanks.value[diff] === undefined) {
      void refreshMyRank(diff)
    }
  })

  return {
    difficultyLeaderboards,
    myRanks,
    hasLoaded,
    loading,
    selectedTab,
    selectedDifficulty,
    refreshScores,
    refreshMyRank,
    prefetchScores,
    startPolling,
    stopPolling
  }
}
