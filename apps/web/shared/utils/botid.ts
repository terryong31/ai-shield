/** Routes protected by Vercel BotID (shared by client plugin and server proxy, spec 0043). */
export interface BotIdProtectedRoute {
  path: string
  method: 'POST'
}

export const BOTID_PROTECTED_ROUTES: readonly BotIdProtectedRoute[] = [
  { path: '/api/v1/auth/anonymous', method: 'POST' },
  { path: '/api/v1/auth/register', method: 'POST' },
  { path: '/api/v1/auth/login', method: 'POST' },
  { path: '/api/v1/game/run', method: 'POST' },
  { path: '/api/v1/game/train', method: 'POST' }
]
