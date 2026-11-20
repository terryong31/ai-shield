import type {
  DifficultyCategory,
  DifficultyLeaderboardEntry,
  LevelId,
  ScoreRecord
} from '~/types/api'

const CACHE_KEY = 'shield_leaderboard_cache_v3'

let inFlightRefresh: Promise<void> | null = null
let streamSource: EventSource | null = null
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let retryTimer: ReturnType<typeof setTimeout> | null = null
let streamSubscribers = 0

export const useLeaderboard = () => {
  const { getScores, getLeaderboard } = useShieldApi()
  const config = useRuntimeConfig()

  const scores = useState<ScoreRecord[]>('shield_leaderboard_scores', () => [])
  const difficultyLeaderboards = useState<Record<DifficultyCategory, DifficultyLeaderboardEntry[]>>(
    'shield_difficulty_leaderboards',
    () => ({
      Easy: [],
      Medium: [],
      Hard: []
    })
  )
  const hasLoaded = useState<boolean>('shield_leaderboard_loaded', () => false)
  const loading = useState<boolean>('shield_leaderboard_loading', () => false)
  const selectedTab = useState<LevelId>('shield_leaderboard_tab', () => 'easy-1')
  const selectedDifficulty = useState<DifficultyCategory>('shield_leaderboard_difficulty', () => 'Easy')

  const clearRetryTimer = () => {
    if (retryTimer) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
  }

  const hydrateFromCache = () => {
    if (!import.meta.client || hasLoaded.value) return
    try {
      const raw = window.sessionStorage.getItem(CACHE_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw) as Partial<Record<DifficultyCategory, DifficultyLeaderboardEntry[]>>
      if (
        Array.isArray(parsed.Easy)
        && Array.isArray(parsed.Medium)
        && Array.isArray(parsed.Hard)
      ) {
        difficultyLeaderboards.value = {
          Easy: parsed.Easy,
          Medium: parsed.Medium,
          Hard: parsed.Hard
        }
        hasLoaded.value = true
      }
    } catch {
      // Ignore corrupt or unavailable sessionStorage.
    }
  }

  const persistToCache = () => {
    if (!import.meta.client) return
    try {
      window.sessionStorage.setItem(CACHE_KEY, JSON.stringify(difficultyLeaderboards.value))
    } catch {
      // Ignore quota or storage errors.
    }
  }

  const refreshRawScores = async (limit = 50) => {
    scores.value = await getScores(undefined, limit)
  }

  const refreshScores = async (options?: { background?: boolean }) => {
    if (inFlightRefresh) return inFlightRefresh
    clearRetryTimer()
    hydrateFromCache()

    const background = options?.background ?? hasLoaded.value
    if (!background && !hasLoaded.value) {
      loading.value = true
    }

    inFlightRefresh = (async () => {
      try {
        const allTabs: DifficultyCategory[] = ['Easy', 'Medium', 'Hard']
        const activeDiff = selectedDifficulty.value
        const activeRows = await getLeaderboard(activeDiff, 25)
        difficultyLeaderboards.value = {
          ...difficultyLeaderboards.value,
          [activeDiff]: activeRows
        }
        hasLoaded.value = true
        loading.value = false
        clearRetryTimer()
        persistToCache()

        const remainingTabs = allTabs.filter(t => t !== activeDiff)
        void Promise.all(
          remainingTabs.map(async (diff) => {
            const rows = await getLeaderboard(diff, 25)
            difficultyLeaderboards.value = {
              ...difficultyLeaderboards.value,
              [diff]: rows
            }
          })
        )
          .then(() => {
            persistToCache()
          })
          .catch((err) => {
            console.warn('Background leaderboard prefetch failed:', err)
          })
      } catch (err) {
        console.warn('Scoreboard unavailable:', err)
        if (!hasLoaded.value && import.meta.client && !retryTimer) {
          retryTimer = setTimeout(() => {
            retryTimer = null
            void refreshScores({ background: true })
          }, 1500)
        }
      } finally {
        loading.value = false
        inFlightRefresh = null
      }
    })()

    return inFlightRefresh
  }

  const scheduleBackgroundRefresh = () => {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      void refreshScores({ background: true })
    }, 300)
  }

  const connectStream = () => {
    if (!import.meta.client || typeof EventSource === 'undefined') return
    streamSubscribers += 1
    if (streamSource) return

    const baseUrl = String(config.public.apiBaseUrl).replace(/\/$/, '')
    const source = new EventSource(`${baseUrl}/api/v1/game/scores/stream`)
    source.addEventListener('open', () => {
      if (!hasLoaded.value) {
        void refreshScores({ background: true })
      }
    })
    source.addEventListener('leaderboard', () => {
      scheduleBackgroundRefresh()
    })
    streamSource = source
  }

  const disconnectStream = () => {
    streamSubscribers = Math.max(0, streamSubscribers - 1)
    if (streamSubscribers > 0) return
    clearRetryTimer()
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    if (streamSource) {
      streamSource.close()
      streamSource = null
    }
  }

  return {
    scores,
    difficultyLeaderboards,
    hasLoaded,
    loading,
    selectedTab,
    selectedDifficulty,
    refreshScores,
    refreshRawScores,
    connectStream,
    disconnectStream
  }
}
