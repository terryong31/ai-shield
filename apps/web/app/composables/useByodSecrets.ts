import type { ByodConfigSchema } from '~/types/api'

export interface ByodSecretState {
  openai_api_key: string
  groq_api_key: string
  gemini_api_key: string
}

export const useByodSecrets = () => {
  const secrets = useState<ByodSecretState>('ai_shield_byod_secrets', () => ({
    openai_api_key: '',
    groq_api_key: '',
    gemini_api_key: ''
  }))

  const byodPayload = computed<ByodConfigSchema>(() => {
    const groqKey = secrets.value.groq_api_key.trim()
    const openaiKey = secrets.value.openai_api_key.trim()
    if (groqKey) {
      return {
        provider: 'groq',
        api_key: groqKey,
        model: null,
        base_url: null
      }
    }
    if (openaiKey) {
      return {
        provider: 'openai',
        api_key: openaiKey,
        model: null,
        base_url: null
      }
    }
    return {
      provider: 'offline',
      api_key: null,
      model: null,
      base_url: null
    }
  })

  return {
    secrets,
    byodPayload
  }
}
