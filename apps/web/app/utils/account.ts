/** Pure rules for the account settings forms (spec 0025, 0036). */

import { isStrongPassword } from './playerAuth'

export const MIN_PASSWORD_LENGTH = 8

export interface PasswordChangeForm {
  current: string
  next: string
  confirm: string
}

/** The password form submits only when the gateway would accept it. */
export function passwordChangeReady(form: PasswordChangeForm): boolean {
  return form.current.length > 0
    && isStrongPassword(form.next)
    && form.next === form.confirm
    && form.next !== form.current
}

/** Deleting needs the exact word, so it cannot happen by accident. */
export function deleteConfirmed(text: string): boolean {
  return text === 'DELETE'
}

/** The gateway's error message, or a generic/custom fallback (spec 0025, 0043). */
export function errorDetail(err: unknown, fallback = 'Something went wrong. Try again.'): string {
  const detail = (err as { data?: { detail?: unknown } }).data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}
