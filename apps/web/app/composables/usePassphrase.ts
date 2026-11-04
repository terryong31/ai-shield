import type { ClearanceStatus } from '~/types/api'

// Older builds kept the raw passphrase here; it is removed on load (spec 0012).
const LEGACY_STORAGE_KEY = 'ai_shield_passphrase'

/**
 * Admin access. The passphrase is sent once to the gateway, which answers with
 * an HttpOnly session cookie; the browser only ever holds the resulting status.
 */
export const usePassphrase = () => {
  const { getClearance, grantClearance, revokeClearance } = useShieldApi()
  const toast = useToast()

  const status = useState<ClearanceStatus>('shield_clearance', () => ({ granted: false, expires_at: null }))
  const granted = computed(() => status.value.granted)
  const tempPassphrase = useState<string>('shield_passphrase_draft', () => '')
  const isModalOpen = useState<boolean>('shield_passphrase_modal', () => false)

  const loadPassphrase = async () => {
    if (!import.meta.client) return
    localStorage.removeItem(LEGACY_STORAGE_KEY)
    try {
      status.value = await getClearance()
    } catch (err) {
      console.warn('Clearance status unavailable:', err)
    }
  }

  const closeModal = () => {
    tempPassphrase.value = ''
    isModalOpen.value = false
  }

  const openModal = () => {
    tempPassphrase.value = ''
    isModalOpen.value = true
  }

  const savePassphrase = async () => {
    const passphrase = tempPassphrase.value.trim()
    if (!passphrase) return
    try {
      status.value = await grantClearance(passphrase)
      closeModal()
    } catch (err) {
      const code = (err as { statusCode?: number }).statusCode
      toast.add({
        title: code === 429 ? 'Too many attempts' : 'Access not granted',
        description: code === 429 ? 'Please wait a few minutes, then try again.' : 'Check the passphrase and try again.',
        icon: 'i-lucide-triangle-alert',
        color: 'neutral'
      })
    } finally {
      tempPassphrase.value = ''
    }
  }

  const clearPassphrase = async () => {
    try {
      await revokeClearance()
    } finally {
      status.value = { granted: false, expires_at: null }
      closeModal()
    }
  }

  const loginWithAuth = async (email: string, password: string) => {
    const cleanPass = password.trim()
    if (!cleanPass) return
    try {
      status.value = await grantClearance(cleanPass, email.trim() || undefined)
      closeModal()
    } catch (err) {
      const code = (err as { statusCode?: number }).statusCode
      toast.add({
        title: code === 429 ? 'Too many attempts' : 'Sign in failed',
        description: code === 429 ? 'Please wait before trying again.' : 'Invalid email or password.',
        icon: 'i-lucide-triangle-alert',
        color: 'neutral'
      })
    }
  }

  return {
    status,
    granted,
    tempPassphrase,
    isModalOpen,
    loadPassphrase,
    openModal,
    closeModal,
    savePassphrase,
    loginWithAuth,
    clearPassphrase
  }
}
