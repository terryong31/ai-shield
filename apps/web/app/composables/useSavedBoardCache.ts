import type { RunLevelId, SavedBoardRequest } from '~/types/api'

export const useSavedBoardCache = () => {
  const cache = useState<Record<string, SavedBoardRequest>>('shield_saved_boards_cache', () => ({}))

  const cacheKey = (owner: string, levelId: RunLevelId) => `${owner}:${levelId}`

  const getCachedBoard = (owner: string, levelId: RunLevelId): SavedBoardRequest | null =>
    cache.value[cacheKey(owner, levelId)] ?? null

  const setCachedBoard = (owner: string, levelId: RunLevelId, board: SavedBoardRequest) => {
    cache.value[cacheKey(owner, levelId)] = board
  }

  const clearSavedBoardCache = () => {
    cache.value = {}
  }

  return {
    getCachedBoard,
    setCachedBoard,
    clearSavedBoardCache
  }
}
