import { initBotId } from 'botid/client/core'
import { BOTID_PROTECTED_ROUTES } from '../../shared/utils/botid'

export default defineNuxtPlugin(() => {
  initBotId({ protect: [...BOTID_PROTECTED_ROUTES] })
})
