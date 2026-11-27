/** Pure rules for the account settings forms (spec 0025, 0036). */

import * as z from 'zod'
import { isStrongPassword } from './playerAuth'

export const MIN_PASSWORD_LENGTH = 8

export const displayNameSchema = z.object({
  name: z.string('Display name is required').trim().min(1, 'Display name is required').max(64, 'Use at most 64 characters')
})

// The Change email form (spec 0053): a valid address and the current password.
export const emailChangeSchema = z.object({
  email: z.email('Enter a valid email address').trim(),
  password: z.string('Enter your current password').min(1, 'Enter your current password')
})

export const EXPORT_FILE_NAME = 'ai-shield-account-export.json'

/** The browser calls the download needs; tests pass fakes (spec 0058). */
export interface DownloadHost {
  createElement: () => { href: string, download: string, click: () => void }
  createObjectURL: (blob: Blob) => string
  revokeObjectURL: (url: string) => void
}

/** Save data as a JSON file through a temporary object URL, revoked straight after. */
export function downloadJson(data: unknown, fileName: string, host: DownloadHost): void {
  const url = host.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
  try {
    const link = host.createElement()
    link.href = url
    link.download = fileName
    link.click()
  } finally {
    host.revokeObjectURL(url)
  }
}

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
