import type { PlayerSessionStatus } from '~/types/api'
import { isConfirmationSent, loginFailure } from '~/utils/playerAuth'

export type RegisterOutcome = 'signed_in' | 'confirmation_sent' | 'failed'
export type SignInOutcome = 'signed_in' | 'unconfirmed' | 'failed'

const DEFAULT_ANONYMOUS_SESSION: PlayerSessionStatus = {
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
  test_runs_used: 0
}

export const usePlayerAuth = () => {
  const {
    getAuthSession,
    signInAnonymously,
    registerPlayer,
    resendConfirmation,
    loginPlayer,
    recoverPlayer,
    upgradePlayer,
    logoutPlayer
  } = useShieldApi()
  const toast = useToast()

  const session = useState<PlayerSessionStatus>(
    'shield_player_session',
    () => ({ ...DEFAULT_ANONYMOUS_SESSION })
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
        password: password.trim()
      })
      toast.add({
        title: 'Signed in',
        description: `Welcome back, ${session.value.player_name}.`,
        icon: 'i-lucide-user-check',
        color: 'neutral'
      })
      return 'signed_in'
    } catch (err) {
      const failure = loginFailure((err as { statusCode?: number }).statusCode)
      if (failure === 'unconfirmed') return 'unconfirmed'
      const detail = (err as { data?: { detail?: string } }).data?.detail ?? 'Invalid email or password.'
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
      const result = await registerPlayer({
        email: email.trim(),
        password: password.trim(),
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
      const detail = (err as { data?: { detail?: string } }).data?.detail ?? 'Could not create account.'
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
        description: 'Check the email address and try again.',
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
      await recoverPlayer({ email: email.trim() })
      toast.add({
        title: 'Recovery email sent',
        description: 'If an account matches that email, a password reset link has been sent.',
        icon: 'i-lucide-mail',
        color: 'neutral'
      })
      return true
    } catch (err) {
      const detail = (err as { data?: { detail?: string } }).data?.detail ?? 'Could not send recovery email.'
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
      const detail = (err as { data?: { detail?: string } }).data?.detail ?? 'Sign in required to upgrade.'
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
    upgradeToPaid,
    signOutPlayer
  }
}
