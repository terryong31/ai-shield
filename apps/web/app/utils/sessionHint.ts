import type { PlayerSessionStatus } from '~/types/api'

/**
 * Display-only copy of the last known player session (spec 0047). It lets the first
 * server render show the right account state; the gateway never reads or trusts it.
 */
export const SESSION_HINT_COOKIE = 'shield_session_hint'
/** Matches the default gateway session lifetime (SESSION_TTL_MINUTES). */
export const SESSION_HINT_MAX_AGE_SECONDS = 480 * 60

export const DEFAULT_ANONYMOUS_SESSION: PlayerSessionStatus = {
  authenticated: false,
  is_anonymous: true,
  tier: 'anonymous',
  email: null,
  player_name: 'Anonymous',
  ai_nodes_allowed: false,
  can_record_scores: false,
  daily_wave_limit: null,
  wave_runs_used: 0,
  daily_test_limit: null,
  test_runs_used: 0,
  daily_train_limit: 0,
  train_runs_used: 0
}

/** Only what the first render needs: no email and no quotas. */
export type SessionHint = Pick<PlayerSessionStatus, 'tier' | 'player_name' | 'ai_nodes_allowed' | 'can_record_scores'>

export function hintFromSession(session: PlayerSessionStatus): SessionHint | null {
  if (!session.authenticated || session.is_anonymous) return null
  const { tier, player_name, ai_nodes_allowed, can_record_scores } = session
  return { tier, player_name, ai_nodes_allowed, can_record_scores }
}

export function sessionFromHint(hint: unknown): PlayerSessionStatus {
  const anonymous = { ...DEFAULT_ANONYMOUS_SESSION }
  if (typeof hint !== 'object' || hint === null) return anonymous
  const { tier, player_name, ai_nodes_allowed, can_record_scores } = hint as Partial<SessionHint>
  if ((tier !== 'free' && tier !== 'paid') || typeof player_name !== 'string') return anonymous
  return {
    ...anonymous,
    authenticated: true,
    is_anonymous: false,
    tier,
    player_name,
    ai_nodes_allowed: ai_nodes_allowed === true,
    can_record_scores: can_record_scores === true
  }
}
