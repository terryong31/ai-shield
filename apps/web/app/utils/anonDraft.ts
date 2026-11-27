import type { LevelId, RunLevelId, SavedBoardRequest } from '../types/api'
import { boardFromSave } from './gameBoard'

/**
 * Local board drafts of anonymous players (spec 0052). A draft holds only the wiring
 * and node positions: never a score, medal, key or token. Scores stay on the gateway.
 */

export const DRAFT_VERSION = 1
export const DRAFT_DEBOUNCE_MS = 400
// The saved-board limits of spec 0023.
const MAX_NODES = 60
const MAX_EDGES = 200
const MAX_BYTES = 256 * 1024

export type DraftStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export type DraftRead
  = | { kind: 'none' }
    | { kind: 'invalid' }
    | { kind: 'ok', save: SavedBoardRequest }

/** What to do with a local draft after sign-in, from the status of `GET /saves/{level}`. */
export type DraftPromotion = 'upload' | 'prompt' | 'discard' | 'keep'

export function draftKey(levelId: RunLevelId): string {
  return `shield_anon_draft:v${DRAFT_VERSION}:${levelId}`
}

/** The browser's localStorage, or `null` where it is blocked (private mode, SSR). */
export function browserDraftStorage(): DraftStorage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
}

export function writeDraft(
  storage: DraftStorage | null,
  levelId: RunLevelId,
  save: SavedBoardRequest,
  now: Date = new Date()
): boolean {
  if (!storage || levelId === 'custom') return false
  if (save.board.nodes.length > MAX_NODES || save.board.edges.length > MAX_EDGES) return false
  const text = JSON.stringify({
    version: DRAFT_VERSION,
    level_id: levelId,
    updated_at: now.toISOString(),
    board: save.board,
    positions: save.positions ?? {}
  })
  if (new Blob([text]).size > MAX_BYTES) return false
  try {
    storage.setItem(draftKey(levelId), text)
    return true
  } catch {
    return false
  }
}

export function readDraft(storage: DraftStorage | null, levelId: LevelId): DraftRead {
  if (!storage) return { kind: 'none' }
  let text: string | null
  try {
    text = storage.getItem(draftKey(levelId))
  } catch {
    return { kind: 'none' }
  }
  if (text === null) return { kind: 'none' }
  try {
    const parsed = JSON.parse(text) as Partial<{
      version: number
      level_id: string
      board: SavedBoardRequest['board']
      positions: SavedBoardRequest['positions']
    }>
    if (parsed.version !== DRAFT_VERSION || parsed.level_id !== levelId) return { kind: 'invalid' }
    if (!parsed.board || !Array.isArray(parsed.board.nodes) || !Array.isArray(parsed.board.edges)) {
      return { kind: 'invalid' }
    }
    // Only the wiring and positions are read, so typed-in score fields are dropped.
    const save: SavedBoardRequest = { board: parsed.board, positions: parsed.positions ?? {}, custom: null }
    return boardFromSave(save, levelId) ? { kind: 'ok', save } : { kind: 'invalid' }
  } catch {
    return { kind: 'invalid' }
  }
}

export function removeDraft(storage: DraftStorage | null, levelId: RunLevelId): void {
  try {
    storage?.removeItem(draftKey(levelId))
  } catch {
    // Blocked storage has nothing to remove.
  }
}

/**
 * 404 (no account save) uploads the draft; 200 asks the player; 403 (level not
 * open on this plan) drops it; any other failure keeps it so no work is lost.
 */
export function draftPromotion(status: number | null): DraftPromotion {
  if (status === 404) return 'upload'
  if (status === 200) return 'prompt'
  if (status === 403) return 'discard'
  return 'keep'
}
