import { SESSION_HINT_COOKIE, SESSION_HINT_MAX_AGE_SECONDS, hintFromSession, type SessionHint } from '~/utils/sessionHint'

// Keeps the hint cookie in step with every session change (spec 0047), and drops the ranks of the previous player.
export default defineNuxtPlugin(() => {
  const { session } = usePlayerAuth()
  const myRanks = useMyRanks()
  const hint = useCookie<SessionHint | null>(SESSION_HINT_COOKIE, {
    maxAge: SESSION_HINT_MAX_AGE_SECONDS,
    path: '/',
    sameSite: 'lax',
    secure: window.location.protocol === 'https:'
  })

  watch(session, (current, previous) => {
    hint.value = hintFromSession(current)
    if (current.is_anonymous !== previous.is_anonymous || current.player_name !== previous.player_name) {
      myRanks.value = {}
    }
  }, { flush: 'sync' })
})
