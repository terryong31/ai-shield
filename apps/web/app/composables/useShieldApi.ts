import type {
  AccountDeleteRequest,
  AccountEmailRequest,
  AccountPasswordRequest,
  AccountResetRequest,
  AccountResetResponse,
  ClearanceStatus,
  DifficultyCategory,
  DifficultyLeaderboardEntry,
  GameCatalogResponse,
  GameRunRequest,
  GameRunResponse,
  GameTrainRequest,
  GameTrainResponse,
  LeaderboardRankResponse,
  LevelId,
  PlayerConfirmationResponse,
  PlayerLoginRequest,
  PlayerProgressResponse,
  PlayerRecoverRequest,
  PlayerRecoverResponse,
  PlayerRegisterRequest,
  PlayerResendRequest,
  PlayerSessionStatus,
  RunLevelId,
  SavedBoardRequest,
  SavedBoardResponse,
  ScoreRecord
} from '~/types/api'

/**
 * The only way the web app talks to the backend. Every shape comes from the
 * generated OpenAPI contract, so a backend change that breaks the client
 * fails `nuxt typecheck`.
 */
export const useShieldApi = () => {
  // Same origin: the web server proxies to the gateway, so the HttpOnly player and
  // admin session cookies are first-party (specs 0012, 0016, 0041).
  const api = $fetch.create({ baseURL: SHIELD_API_PREFIX, credentials: 'include' })

  return {
    getClearance: () => api<ClearanceStatus>('/clearance'),
    grantClearance: (email: string, password: string) =>
      api<ClearanceStatus>('/clearance', { method: 'POST', body: { email, password } }),
    revokeClearance: () => api('/clearance', { method: 'DELETE' }),
    getAuthSession: () => api<PlayerSessionStatus>('/auth/session'),
    signInAnonymously: () => api<PlayerSessionStatus>('/auth/anonymous', { method: 'POST' }),
    // 200 signs the player in; 202 means "check your email" (spec 0027).
    registerPlayer: (body: PlayerRegisterRequest) =>
      api<PlayerSessionStatus | PlayerConfirmationResponse>('/auth/register', { method: 'POST', body }),
    resendConfirmation: (body: PlayerResendRequest) =>
      api<PlayerConfirmationResponse>('/auth/resend-confirmation', { method: 'POST', body }),
    loginPlayer: (body: PlayerLoginRequest) =>
      api<PlayerSessionStatus>('/auth/login', { method: 'POST', body }),
    recoverPlayer: (body: PlayerRecoverRequest) =>
      api<PlayerRecoverResponse>('/auth/recover', { method: 'POST', body }),
    upgradePlayer: () => api<PlayerSessionStatus>('/auth/upgrade', { method: 'POST' }),
    logoutPlayer: () => api('/auth/logout', { method: 'POST' }),
    // Account settings (spec 0025); each needs the current password.
    changePassword: (body: AccountPasswordRequest) =>
      api<PlayerSessionStatus>('/auth/account/password', { method: 'POST', body }),
    changeEmail: (body: AccountEmailRequest) =>
      api<PlayerConfirmationResponse>('/auth/account/email', { method: 'POST', body }),
    resetProgress: (body: AccountResetRequest) =>
      api<AccountResetResponse>('/auth/account/reset-progress', { method: 'POST', body }),
    deleteAccount: (body: AccountDeleteRequest) =>
      api('/auth/account', { method: 'DELETE', body }),
    getLevels: () => api<GameCatalogResponse>('/game/levels'),
    runGame: (body: GameRunRequest) =>
      api<GameRunResponse>('/game/run', { method: 'POST', body }),
    trainClassifier: (body: GameTrainRequest) =>
      api<GameTrainResponse>('/game/train', { method: 'POST', body }),
    purgeModels: () => api('/game/models', { method: 'DELETE' }),
    getSave: (levelId: RunLevelId) =>
      api<SavedBoardResponse>(`/game/saves/${levelId}`),
    putSave: (levelId: RunLevelId, body: SavedBoardRequest) =>
      api<SavedBoardResponse>(`/game/saves/${levelId}`, { method: 'PUT', body }),
    getLeaderboard: (difficulty: DifficultyCategory = 'Easy', limit = 25) =>
      api<DifficultyLeaderboardEntry[]>('/game/leaderboard', {
        query: { difficulty, limit }
      }),
    getMyLeaderboardRank: (difficulty: DifficultyCategory = 'Easy') =>
      api<LeaderboardRankResponse>('/game/leaderboard/me', {
        query: { difficulty }
      }),
    getProgress: () =>
      api<PlayerProgressResponse>('/game/progress'),
    getScores: (levelId?: LevelId, limit = 25) =>
      api<ScoreRecord[]>('/game/scores', {
        query: levelId ? { level_id: levelId, limit } : { limit }
      }),
    clearScores: () => api('/game/scores', { method: 'DELETE' })
  }
}
