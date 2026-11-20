import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { hasSeenTour, levelTourSteps, markTourSeen, tourSeenKey } from '../app/utils/levelTours'

const APP_DIR = join(import.meta.dirname, '..', 'app')
const read = (...parts: string[]) => readFileSync(join(APP_DIR, ...parts), 'utf-8')

describe('introductory level tours (spec 0040)', () => {
  it('[WEB-CAMP-007] defines a tour for each introductory level that points at the nodes it teaches', () => {
    const taught: Record<string, string[]> = {
      'easy-1': ['word_filter', 'length_limit'],
      'easy-2': ['text_cleanup', 'secret_scan'],
      'easy-3': ['ml_classifier']
    }
    for (const [levelId, kinds] of Object.entries(taught)) {
      const steps = levelTourSteps(levelId)
      const targets = steps.map(s => s.target)

      expect(steps[0]?.target).toBeNull()
      for (const kind of kinds) expect(targets).toContain(`[data-tour="tool-${kind}"]`)
      expect(targets).toContain('[data-tour="test-bar"]')
      expect(targets.at(-1)).toBe('[data-tour="run-wave"]')
      for (const step of steps) {
        expect(step.title.length).toBeGreaterThan(0)
        expect(step.body.length).toBeGreaterThan(0)
      }
    }
    expect(levelTourSteps('easy-3').map(s => s.target)).toContain('[data-tour="node-ml_classifier"]')
    expect(levelTourSteps('medium-1')).toEqual([])
    expect(levelTourSteps('custom')).toEqual([])
    expect(tourSeenKey('easy-3')).toBe('ai-shield:tour-seen:easy-3')
  })

  it('[WEB-CAMP-007] remembers a finished tour and tolerates blocked storage', () => {
    const store = new Map<string, string>()
    const storage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v)
    }
    const blocked = {
      getItem: () => { throw new Error('blocked') },
      setItem: () => { throw new Error('blocked') }
    }

    expect(hasSeenTour('easy-3', storage)).toBe(false)
    markTourSeen('easy-3', storage)
    expect(hasSeenTour('easy-3', storage)).toBe(true)
    expect(hasSeenTour('easy-2', storage)).toBe(false)
    expect(() => markTourSeen('easy-3', blocked)).not.toThrow()
    expect(hasSeenTour('easy-3', blocked)).toBe(false)
  })

  it('[WEB-CAMP-007] runs the tour on /game with useTour, one UPopover and a Guide button', () => {
    const gameSource = read('pages', 'game.vue')
    const nodeSource = read('components', 'workflow', 'GameNode.vue')

    expect(gameSource).toMatch(/useTour\(/)
    expect(gameSource).toContain('levelTourSteps(currentLevelId.value)')
    expect(gameSource).toContain('hasSeenTour(currentLevelId.value)')
    expect(gameSource).toContain('markTourSeen(currentLevelId.value)')
    expect(gameSource.match(/<UPopover/g)?.length).toBe(1)
    expect(gameSource).toContain(':reference="tour.reference.value"')
    expect(gameSource).toContain(':dismissible="false"')
    expect(gameSource).toMatch(/v-if="hasLevelTour"[\s\S]*?label="Guide"/)
    for (const label of ['label="Back"', 'label="Skip"', '\'Finish\' : \'Next\'']) expect(gameSource).toContain(label)
    expect(gameSource).toContain('[data-tour="canvas"]')
    for (const target of ['data-tour="run-wave"', 'data-tour="test-bar"', 'data-tour="canvas"']) expect(gameSource).toContain(target)
    expect(gameSource).toContain(':data-tour="`tool-${chk.kind}`"')
    expect(nodeSource).toContain(':data-tour="`node-${data.kind}`"')
  })
})
