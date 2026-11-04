import type { SecurityMode } from '~/types/api'

const STORAGE_KEY = 'ai_shield_security_mode'
const MODES: SecurityMode[] = ['shield', 'guardrail', 'chaos']

/** Operating mode shared by the settings page and the chat, persisted per browser. */
export const useSecurityMode = () => {
  const mode = useState<SecurityMode>('shield_security_mode', () => 'shield')

  const load = () => {
    if (!import.meta.client) return
    const saved = localStorage.getItem(STORAGE_KEY) as SecurityMode | null
    if (saved && MODES.includes(saved)) mode.value = saved
  }

  const set = (value: SecurityMode) => {
    mode.value = value
    if (import.meta.client) localStorage.setItem(STORAGE_KEY, value)
  }

  return { mode, load, set }
}
