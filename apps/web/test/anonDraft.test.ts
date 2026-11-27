import { describe, expect, it } from 'vitest'
import {
  DRAFT_DEBOUNCE_MS,
  draftKey,
  draftPromotion,
  readDraft,
  removeDraft,
  writeDraft,
  type DraftStorage
} from '../app/utils/anonDraft'
import { createStarterBoard, saveFromBoard } from '../app/utils/gameBoard'
import { readGamePage } from './support/gameSource'

const page = readGamePage()

function memoryStorage(): DraftStorage & { data: Map<string, string> } {
  const data = new Map<string, string>()
  return {
    data,
    getItem: key => data.get(key) ?? null,
    setItem: (key, value) => {
      data.set(key, value)
    },
    removeItem: (key) => {
      data.delete(key)
    }
  }
}

function throwingStorage(name: string): DraftStorage {
  const fail = () => {
    throw new DOMException('blocked', name)
  }
  return { getItem: fail, setItem: fail, removeItem: fail }
}

const starterSave = () => saveFromBoard(createStarterBoard('easy-1'))

describe('Anonymous board drafts (spec 0052)', () => {
  it('[WEB-DRAFT-001] writes a versioned draft per level and reads it back after a reload', () => {
    const storage = memoryStorage()
    const save = starterSave()
    save.positions.incoming = { x: 40, y: 200 }

    expect(writeDraft(storage, 'easy-1', save, new Date('2026-11-26T12:00:00.000Z'))).toBe(true)
    expect(draftKey('easy-1')).toBe('shield_anon_draft:v1:easy-1')
    const stored = JSON.parse(storage.data.get('shield_anon_draft:v1:easy-1')!)
    expect(stored).toMatchObject({ version: 1, level_id: 'easy-1', updated_at: '2026-11-26T12:00:00.000Z' })
    expect(Object.keys(stored).sort()).toEqual(['board', 'level_id', 'positions', 'updated_at', 'version'])

    const read = readDraft(storage, 'easy-1')
    expect(read.kind).toBe('ok')
    if (read.kind === 'ok') {
      expect(read.save.positions.incoming).toEqual({ x: 40, y: 200 })
      expect(read.save.board).toEqual(save.board)
    }
    expect(readDraft(storage, 'easy-2').kind).toBe('none')

    expect(DRAFT_DEBOUNCE_MS).toBe(400)
    expect(page).toMatch(/writeDraft\(/)
    expect(page).toMatch(/readDraft\(/)
    expect(page).toMatch(/DRAFT_DEBOUNCE_MS/)
  })

  it('[WEB-DRAFT-001] never writes drafts for the custom level or over the save limits', () => {
    const storage = memoryStorage()
    expect(writeDraft(storage, 'custom', starterSave())).toBe(false)
    const big = starterSave()
    big.board.nodes = Array.from({ length: 61 }, (_, i) => ({ id: `n${i}`, kind: 'word_filter', config: {} }))
    expect(writeDraft(storage, 'easy-1', big)).toBe(false)
    expect(storage.data.size).toBe(0)
  })

  it('[WEB-DRAFT-002] Restart removes the level draft', () => {
    const storage = memoryStorage()
    writeDraft(storage, 'easy-1', starterSave())
    removeDraft(storage, 'easy-1')
    expect(storage.data.has(draftKey('easy-1'))).toBe(false)
    expect(page).toMatch(/const handleRestart = \(\) => \{[\s\S]*?resetBoard\(\)[\s\S]*?removeDraft\(/)
    expect(page).toMatch(/@click="handleRestart"/)
  })

  it('[WEB-DRAFT-003] falls back cleanly on corrupt drafts, old versions and blocked storage', () => {
    const storage = memoryStorage()
    storage.data.set(draftKey('easy-1'), '{not json')
    expect(readDraft(storage, 'easy-1').kind).toBe('invalid')

    storage.data.set(draftKey('easy-1'), JSON.stringify({ version: 9, level_id: 'easy-1', board: starterSave().board, positions: {} }))
    expect(readDraft(storage, 'easy-1').kind).toBe('invalid')

    const removedKind = starterSave()
    removedKind.board.nodes.push({ id: 'x', kind: 'quick_screen', config: {} })
    storage.data.set(draftKey('easy-1'), JSON.stringify({ version: 1, level_id: 'easy-1', board: removedKind.board, positions: {} }))
    expect(readDraft(storage, 'easy-1').kind).toBe('invalid')

    for (const name of ['QuotaExceededError', 'SecurityError']) {
      const blocked = throwingStorage(name)
      expect(() => writeDraft(blocked, 'easy-1', starterSave())).not.toThrow()
      expect(writeDraft(blocked, 'easy-1', starterSave())).toBe(false)
      expect(readDraft(blocked, 'easy-1').kind).toBe('none')
      expect(() => removeDraft(blocked, 'easy-1')).not.toThrow()
    }
    expect(readDraft(null, 'easy-1').kind).toBe('none')
  })

  it('[WEB-DRAFT-004] uploads the draft when the account has no save, then clears it', () => {
    expect(draftPromotion(404)).toBe('upload')
    expect(page).toMatch(/draftPromotion\(/)
    expect(page).toMatch(/Your local board was saved to your account\./)
  })

  it('[WEB-DRAFT-005] asks before replacing an existing account save', () => {
    expect(draftPromotion(200)).toBe('prompt')
    expect(page).toMatch(/label="Keep local board"/)
    expect(page).toMatch(/label="Use saved board"/)
  })

  it('[WEB-DRAFT-006] keeps the draft when the upload fails, and skips forbidden levels', () => {
    expect(draftPromotion(500)).toBe('keep')
    expect(draftPromotion(null)).toBe('keep')
    expect(draftPromotion(403)).toBe('discard')
  })

  it('[WEB-DRAFT-007] writes drafts only for an anonymous player whose draft was loaded', () => {
    expect(page).toMatch(/draftReadyLevel\.value === currentLevelId\.value/)
    expect(page).toMatch(/watch\(isAnonymous, \(\) => \{\s*draftReadyLevel\.value = null/)
  })

  it('[WEB-DRAFT-001] ignores score fields that someone typed into a draft', () => {
    const storage = memoryStorage()
    storage.data.set(draftKey('easy-1'), JSON.stringify({
      version: 1,
      level_id: 'easy-1',
      board: starterSave().board,
      positions: {},
      score: 10000,
      medal: 'gold',
      won: true,
      mastered: true
    }))
    const read = readDraft(storage, 'easy-1')
    expect(read.kind).toBe('ok')
    if (read.kind === 'ok') expect(Object.keys(read.save).sort()).toEqual(['board', 'custom', 'positions'])
  })
})
