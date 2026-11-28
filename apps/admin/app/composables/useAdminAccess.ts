import type { ClearanceStatus } from '~/types/api'

export const useAdminAccess = () => {
  const { getClearance, grantClearance, revokeClearance } = useShieldApi()
  const toast = useToast()

  const status = useState<ClearanceStatus>('shield_clearance', () => ({ granted: false, expires_at: null }))
  const granted = computed(() => status.value.granted)

  const loadAccess = async () => {
    if (!import.meta.client) return
    try {
      status.value = await getClearance()
    } catch (err) {
      console.warn('Clearance status unavailable:', err)
    }
  }

  const signIn = async (email: string, password: string) => {
    if (!email.trim() || !password) return
    try {
      status.value = await grantClearance(email.trim(), password)
    } catch (err) {
      const code = (err as { statusCode?: number }).statusCode
      toast.add({
        title: code === 429 ? 'Too many attempts' : 'Sign in failed',
        description: code === 429 ? 'Please wait a few minutes, then try again.' : 'Check the email and password, and that the account is an admin.',
        icon: 'i-lucide-triangle-alert',
        color: 'neutral'
      })
    }
  }

  const signOut = async () => {
    try {
      await revokeClearance()
    } finally {
      status.value = { granted: false, expires_at: null }
    }
  }

  return { status, granted, loadAccess, signIn, signOut }
}
