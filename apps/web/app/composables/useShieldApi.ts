import type {
  AuditRecord,
  ChatEvent,
  ChatRequest,
  ClearanceStatus,
  FeedbackRequest,
  FeedbackResponse,
  GameCatalogResponse,
  GameRunRequest,
  GameRunResponse,
  GameTrainRequest,
  GameTrainResponse,
  LevelId,
  PlayerLoginRequest,
  PlayerRecoverRequest,
  PlayerRecoverResponse,
  PlayerRegisterRequest,
  PlayerSessionStatus,
  RunLevelId,
  SavedBoardRequest,
  SavedBoardResponse,
  ScoreCreateRequest,
  ScoreRecord,
  Stats
} from '~/types/api'
import { parseNdjson } from '~/utils/chatStream'

/**
 * The only way the web app talks to the backend. Every shape comes from the
 * generated OpenAPI contract, so a backend change that breaks the client
 * fails `nuxt typecheck`.
 */
export const useShieldApi = () => {
  const baseURL = `${useRuntimeConfig().public.apiBaseUrl}/api/v1`
  // Credentials carry the HttpOnly clearance session cookie (spec 0012).
  const api = $fetch.create({ baseURL, credentials: 'include' })

  async function* streamChat(body: ChatRequest, signal?: AbortSignal): AsyncGenerator<ChatEvent> {
    const response = await fetch(`${baseURL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      credentials: 'include',
      signal
    })
    if (!response.ok || !response.body) {
      throw new Error(`Chat request failed with HTTP ${response.status}`)
    }

    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const { events, errors, rest } = parseNdjson(buffer + value)
      buffer = rest
      for (const line of errors) console.warn('Skipping malformed stream line:', line)
      yield* events
    }
    // A final line without a trailing newline is still a complete event.
    if (buffer.trim()) yield* parseNdjson(`${buffer}\n`).events
  }

  return {
    streamChat,
    listRequests: (limit = 30) => api<AuditRecord[]>('/requests', { query: { limit } }),
    getStats: () => api<Stats>('/stats'),
    getClearance: () => api<ClearanceStatus>('/clearance'),
    grantClearance: (passphrase: string, email?: string) =>
      api<ClearanceStatus>('/clearance', { method: 'POST', body: { passphrase, email: email ?? null } }),
    revokeClearance: () => api('/clearance', { method: 'DELETE' }),
    getAuthSession: () => api<PlayerSessionStatus>('/auth/session'),
    signInAnonymously: () => api<PlayerSessionStatus>('/auth/anonymous', { method: 'POST' }),
    registerPlayer: (body: PlayerRegisterRequest) =>
      api<PlayerSessionStatus>('/auth/register', { method: 'POST', body }),
    loginPlayer: (body: PlayerLoginRequest) =>
      api<PlayerSessionStatus>('/auth/login', { method: 'POST', body }),
    recoverPlayer: (body: PlayerRecoverRequest) =>
      api<PlayerRecoverResponse>('/auth/recover', { method: 'POST', body }),
    upgradePlayer: () => api<PlayerSessionStatus>('/auth/upgrade', { method: 'POST' }),
    logoutPlayer: () => api('/auth/logout', { method: 'POST' }),
    sendFeedback: (body: FeedbackRequest) =>
      api<FeedbackResponse>('/feedback', { method: 'POST', body }),
    getLevels: () => api<GameCatalogResponse>('/game/levels'),
    runGame: (body: GameRunRequest) =>
      api<GameRunResponse>('/game/run', { method: 'POST', body }),
    trainClassifier: (body: GameTrainRequest) =>
      api<GameTrainResponse>('/game/train', { method: 'POST', body }),
    getSave: (levelId: RunLevelId) =>
      api<SavedBoardResponse>(`/game/saves/${levelId}`),
    putSave: (levelId: RunLevelId, body: SavedBoardRequest) =>
      api<SavedBoardResponse>(`/game/saves/${levelId}`, { method: 'PUT', body }),
    getScores: (levelId?: LevelId, limit = 25) =>
      api<ScoreRecord[]>('/game/scores', {
        query: levelId ? { level_id: levelId, limit } : { limit }
      }),
    submitScore: (body: ScoreCreateRequest) =>
      api<ScoreRecord>('/game/scores', { method: 'POST', body }),
    clearScores: () => api('/game/scores', { method: 'DELETE' })
  }
}
