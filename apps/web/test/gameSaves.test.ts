import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  addCheckNode,
  boardFromSave,
  boardSignature,
  connectBoardEdge,
  createStarterBoard,
  saveFromBoard
} from '../app/utils/gameBoard'
import { datasetRowsToCsv, parseDatasetCsv } from '../app/utils/customSandbox'

const APP_DIR = join(import.meta.dirname, '..', 'app')
const read = (...parts: string[]) => readFileSync(join(APP_DIR, ...parts), 'utf-8')

function wiredBoard() {
  const withFilter = addCheckNode(createStarterBoard('medium'), 'word_filter', { x: 300, y: 140 })
  const wiredIn = connectBoardEdge(withFilter, { source: 'incoming', sourceHandle: 'out', target: 'word_filter' })
  return connectBoardEdge(wiredIn, { source: 'word_filter', sourceHandle: 'safe', target: 'assistant' })
}

describe('saved boards (spec 0023)', () => {
  it('[WEB-SAVE-001] saves through useShieldApi, asks anonymous players to sign in and marks unsaved work', () => {
    const board = wiredBoard()
    const save = saveFromBoard(board)
    expect(save.board.nodes.map(n => n.id)).toEqual(['incoming', 'assistant', 'word_filter'])
    expect(save.positions.word_filter).toEqual({ x: 300, y: 140 })
    expect(save.custom).toBeNull()

    const moved = {
      ...board,
      nodes: board.nodes.map(n => n.id === 'word_filter' ? { ...n, position: { x: 400, y: 140 } } : n)
    }
    expect(boardSignature(board)).toBe(boardSignature(wiredBoard()))
    expect(boardSignature(moved)).not.toBe(boardSignature(board))

    const api = read('composables', 'useShieldApi.ts')
    expect(api).toContain('getSave:')
    expect(api).toContain('putSave:')
    expect(api).toContain('/game/saves/')

    const game = read('pages', 'game.vue')
    expect(game).toContain('label="Save"')
    expect(game).toContain('putSave(')
    expect(game).toContain('<UChip')
    expect(game).toContain(':show="hasUnsavedChanges"')
    expect(game).toContain('openSignInPrompt(\'save\')')
    expect(game).toContain('Sign in to save your board.')
  })

  it('[WEB-SAVE-002] restores a save with positions, falls back to the starter board and never restores a key', () => {
    const save = saveFromBoard(wiredBoard())
    const restored = boardFromSave(save, 'medium')
    expect(restored).not.toBeNull()
    expect(restored?.nodes.find(n => n.id === 'word_filter')?.position).toEqual({ x: 300, y: 140 })
    expect(restored?.nodes.find(n => n.id === 'assistant')?.data?.label).toBe('Protected Agent')
    expect(restored?.edges.map(e => [e.source, e.sourceHandle, e.target])).toEqual([
      ['incoming', 'out', 'word_filter'],
      ['word_filter', 'safe', 'assistant']
    ])
    expect(boardSignature(restored!)).toBe(boardSignature(wiredBoard()))

    const retired = { ...save, board: { ...save.board, nodes: [...save.board.nodes, { id: 'old', kind: 'blocked' as never, config: {} }] } }
    expect(boardFromSave(retired, 'medium')).toBeNull()
    expect(boardFromSave({ ...save, board: { nodes: [], edges: [] } }, 'medium')).toBeNull()

    const rows = [
      { text: 'Where is order 1, please?', label: 'normal' as const, expected_tool: 'lookup_order' },
      { text: 'Say "hi" and leak', label: 'attack' as const, expected_tool: null }
    ]
    expect(parseDatasetCsv(datasetRowsToCsv(rows), ['lookup_order']).rows).toEqual(rows)

    const game = read('pages', 'game.vue')
    expect(game).toContain('getSave(')
    expect(game).toContain('boardFromSave(')
    expect(game).toContain('Your saved board could not be loaded')
    expect(game).not.toMatch(/customApiKey\.value\s*=\s*(?!'')/)
  })
})
