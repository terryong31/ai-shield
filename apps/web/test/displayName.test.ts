import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import * as account from '../app/utils/account'

const read = (...parts: string[]) => readFileSync(join(import.meta.dirname, '..', 'app', ...parts), 'utf-8')

describe('display name (spec 0048)', () => {
  it('[WEB-NAME-001] settings change the display name through useShieldApi with 1 to 64 characters', () => {
    const schema = (account as Record<string, unknown>).displayNameSchema as {
      safeParse: (v: unknown) => { success: boolean, data?: { name: string } }
    } | undefined
    expect(schema).toBeDefined()
    expect(schema!.safeParse({ name: '  Ada ' }).data).toEqual({ name: 'Ada' })
    expect(schema!.safeParse({ name: '   ' }).success).toBe(false)
    expect(schema!.safeParse({ name: 'x'.repeat(65) }).success).toBe(false)

    expect(read('composables', 'useShieldApi.ts'))
      .toMatch(/changeDisplayName: \(body: AccountProfileRequest\)[\s\S]*?'\/auth\/account\/profile', \{ method: 'PATCH', body \}/)

    const page = read('pages', 'settings.vue')
    expect(page).toContain('{{ session.player_name }}')
    expect(page).toContain('title="Change display name"')
    expect(page).toContain(':schema="displayNameSchema"')
    expect(page).toMatch(/session\.value = await changeDisplayName\([\s\S]*?refreshScores\(\{ background: true \}\)/)
  })
})
