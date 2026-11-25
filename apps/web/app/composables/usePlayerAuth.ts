import type {
  PlayerConfirmRequest,
  PlayerConfirmResponse,
  PlayerResetPasswordRequest,
  PlayerSessionStatus
} from '~/types/api'
import { errorDetail } from '~/utils/account'
import { ensureAuthBrowserCookie, isConfirmationSent, loginFailure } from '~/utils/playerAuth'
import { DEFAULT_ANONYMOUS_SESSION, SESSION_HINT_COOKIE, sessionFromHint } from '~/utils/sessionHint'

export type RegisterOutcome = 'signed_in' | 'confirmation_sent' | 'failed'
export type SignInOutcome = 'signed_in' | 'unconfirmed' | 'failed'

export const usePlayerAuth = () => {
  const {
    getAuthSession,
    signInAnonymously,
    registerPlayer,
    resendConfirmation,
    loginPlayer,
    recoverPlayer,
    confirmEmail: confirmEmailApi,
    resetPassword: resetPasswordApi,
    upgradePlayer,
    logoutPlayer
  } = useShieldApi()
  const toast = useToast()

  const session = useState<PlayerSessionStatus>(
    'shield_player_session',
    () => sessionFromHint(useCookie<unknown>(SESSION_HINT_COOKIE, { readonly: true }).value)
  )
  const loadingAuth = useState<boolean>('shield_player_auth_loading', () => false)

  const isAnonymous = computed(() => session.value.is_anonymous)
  const isLoggedIn = computed(() => !session.value.is_anonymous && session.value.authenticated)
  const isPaid = computed(() => session.value.tier === 'paid')

  const refreshSession = async () => {
    try {
      session.value = await getAuthSession()
    } catch (err) {
      console.warn('Player session unavailable:', err)
    }
  }

  const continueAnonymously = async () => {
    loadingAuth.value = true
    try {
      session.value = await signInAnonymously()
    } catch (err) {
      console.warn('Anonymous sign-in failed:', err)
    } finally {
      loadingAuth.value = false
    }
  }

  const signInWithPassword = async (email: string, password: string): Promise<SignInOutcome> => {
    loadingAuth.value = true
    try {
      session.value = await loginPlayer({
        email: email.trim(),
        password
      })
      toast.add({
        title: 'Signed in',
        description: `Welcome back, ${session.value.player_name}.`,
        icon: 'i-lucide-user-check',
        color: 'neutral'
      })
      return 'signed_in'
    } catch (err) {
      const detail = errorDetail(err, 'Invalid email or password.')
      const failure = loginFailure((err as { statusCode?: number }).statusCode, detail)
      if (failure === 'unconfirmed') return 'unconfirmed'
      toast.add({
        title: 'Sign in failed',
        description: detail,
        icon: 'i-lucide-triangle-alert',
        color: 'neutral'
      })
      return 'failed'
    } finally {
      loadingAuth.value = false
    }
  }

  const registerAccount = async (email: string, password: string, playerName?: string): Promise<RegisterOutcome> => {
    loadingAuth.value = true
    try {
      ensureAuthBrowserCookie()
      const result = await registerPlayer({
        email: email.trim(),
        password,
        player_name: playerName?.trim() || null
      })
      if (isConfirmationSent(result)) return 'confirmation_sent'
      session.value = result
      toast.add({
        title: 'Account created',
        description: `Signed in as ${session.value.player_name}.`,
        icon: 'i-lucide-user-plus',
        color: 'neutral'
      })
      return 'signed_in'
    } catch (err) {
      const detail = errorDetail(err, 'Could not create account.')
      toast.add({
        title: 'Registration failed',
        description: detail,
        icon: 'i-lucide-triangle-alert',
        color: 'neutral'
      })
      return 'failed'
    } finally {
      loadingAuth.value = false
    }
  }

  const resendConfirmationEmail = async (email: string) => {
    loadingAuth.value = true
    try {
      ensureAuthBrowserCookie()
      await resendConfirmation({ email: email.trim() })
      toast.add({
        title: 'Email sent',
        description: 'If that address needs confirming, a new link is on its way.',
        icon: 'i-lucide-mail',
        color: 'neutral'
      })
    } catch (err) {
      console.warn('Resend failed:', err)
      toast.add({
        title: 'Could not resend',
        description: errorDetail(err, 'Check the email address and try again.'),
        icon: 'i-lucide-triangle-alert',
        color: 'neutral'
      })
    } finally {
      loadingAuth.value = false
    }
  }

  const recoverPassword = async (email: string): Promise<boolean> => {
    loadingAuth.value = true
    try {
      ensureAuthBrowserCookie()
      await recoverPlayer({ email: email.trim() })
      toast.add({
        title: 'Recovery email sent',
        description: 'If an account matches that email, a password reset link has been sent.',
        icon: 'i-lucide-mail',
        color: 'neutral'
      })
      return true
    } catch (err) {
      const detail = errorDetail(err, 'Could not send recovery email.')
      toast.add({
        title: 'Recovery failed',
        description: detail,
        icon: 'i-lucide-triangle-alert',
        color: 'neutral'
      })
      return false
    } finally {
      loadingAuth.value = false
    }
  }

  const confirmEmail = async (body: PlayerConfirmRequest): Promise<PlayerConfirmResponse> => {
    loadingAuth.value = true
    try {
      const result = await confirmEmailApi(body)
      if (result.status === 'signed_in' && result.session) {
        session.value = result.session
      }
      return result
    } finally {
      loadingAuth.value = false
    }
  }

  const resetPassword = async (body: PlayerResetPasswordRequest): Promise<boolean> => {
    loadingAuth.value = true
    try {
      await resetPasswordApi(body)
      session.value = { ...DEFAULT_ANONYMOUS_SESSION }
      toast.add({
        title: 'Password reset',
        description: 'Your password has been updated. Sign in with your new password.',
        icon: 'i-lucide-key-round',
        color: 'neutral'
      })
      return true
    } catch (err) {
      toast.add({
        title: 'Reset failed',
        description: errorDetail(err, 'This recovery link is invalid or has expired.'),
        icon: 'i-lucide-triangle-alert',
        color: 'neutral'
      })
      return false
    } finally {
      loadingAuth.value = false
    }
  }

  const upgradeToPaid = async () => {
    loadingAuth.value = true
    try {
      session.value = await upgradePlayer()
      toast.add({
        title: 'Plan upgraded',
        description: '300 wave runs and 1,000 tests a day, plus the custom sandbox.',
        icon: 'i-lucide-sparkles',
        color: 'neutral'
      })
    } catch (err) {
      const detail = errorDetail(err, 'Sign in required to upgrade.')
      toast.add({
        title: 'Could not upgrade',
        description: detail,
        icon: 'i-lucide-triangle-alert',
        color: 'neutral'
      })
    } finally {
      loadingAuth.value = false
    }
  }

  const signOutPlayer = async () => {
    loadingAuth.value = true
    try {
      await logoutPlayer()
      session.value = { ...DEFAULT_ANONYMOUS_SESSION }
      useSavedBoardCache().clearSavedBoardCache()
      toast.add({
        title: 'Signed out',
        description: 'Logged out successfully.',
        icon: 'i-lucide-log-out',
        color: 'neutral'
      })
    } finally {
      loadingAuth.value = false
    }
  }

  return {
    session,
    isAnonymous,
    isLoggedIn,
    isPaid,
    loadingAuth,
    refreshSession,
    continueAnonymously,
    signInWithPassword,
    registerAccount,
    resendConfirmationEmail,
    recoverPassword,
    confirmEmail,
    resetPassword,
    upgradeToPaid,
    signOutPlayer
  }
}
