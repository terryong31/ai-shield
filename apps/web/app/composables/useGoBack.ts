import { hasInAppHistory } from '~/utils/navigation'

/**
 * Back/Return buttons and post-action redirects return to the page the player
 * came from, like the browser's back button; with no previous in-app page they
 * replace the current entry with `fallback` (WEB-GAME-015).
 */
export const useGoBack = () => {
  const router = useRouter()

  return async (fallback = '/') => {
    if (import.meta.client && hasInAppHistory(window.history.state)) {
      router.back()
      return
    }
    await navigateTo(fallback, { replace: true })
  }
}
