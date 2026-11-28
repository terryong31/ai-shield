import type { ClearanceStatus, ScoreRecord } from '~/types/api'

const API_BASE = '/api/v1'

export const useShieldApi = () => {
  const getClearance = async (): Promise<ClearanceStatus> =>
    $fetch<ClearanceStatus>(`${API_BASE}/clearance`, { credentials: 'include' })

  const grantClearance = async (email: string, password: string): Promise<ClearanceStatus> =>
    $fetch<ClearanceStatus>(`${API_BASE}/clearance`, {
      method: 'POST',
      body: { email, password },
      credentials: 'include'
    })

  const revokeClearance = async (): Promise<void> => {
    await $fetch(`${API_BASE}/clearance`, {
      method: 'DELETE',
      credentials: 'include'
    })
  }

  const getScores = async (levelId?: string, limit = 100): Promise<ScoreRecord[]> => {
    const query: Record<string, string | number> = { limit }
    if (levelId) query.level_id = levelId
    return $fetch<ScoreRecord[]>(`${API_BASE}/game/scores`, {
      query,
      credentials: 'include'
    })
  }

  const clearScores = async (): Promise<void> => {
    await $fetch(`${API_BASE}/game/scores`, {
      method: 'DELETE',
      credentials: 'include'
    })
  }

  return { getClearance, grantClearance, revokeClearance, getScores, clearScores }
}
