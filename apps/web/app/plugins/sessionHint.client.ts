import { SESSION_HINT_COOKIE, SESSION_HINT_MAX_AGE_SECONDS, hintFromSession, type SessionHint } from '~/utils/sessionHint'

// Keeps the hint cookie in step with every session change (spec 0047).
export default defineNuxtPlugin(() => {
  const { session } = usePlayerAuth()
  const hint = useCookie<SessionHint | null>(SESSION_HINT_COOKIE, {
    maxAge: SESSION_HINT_MAX_AGE_SECONDS,
    path: '/',
    sameSite: 'lax',
    secure: window.location.protocol === 'https:'
  })
  watch(session, (current) => {
    hint.value = hintFromSession(current)
  })
})
