import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const APP = join(import.meta.dirname, '..', '..', 'app')

// The game page's pieces in their original order (spec 0055): the state and logic
// first, then the page, then each panel in the order the page shows it.
const PARTS = [
  ['composables', 'useGamePage.ts'],
  ['pages', 'game.vue'],
  ['components', 'game', 'Controls.vue'],
  ['components', 'game', 'ToolsPanel.vue'],
  ['components', 'game', 'Canvas.vue'],
  ['components', 'game', 'Dialogs.vue'],
  ['components', 'game', 'ResultsModals.vue'],
  ['components', 'game', 'NodeSettingsModal.vue'],
  ['components', 'game', 'LevelTour.vue']
] as const

/** The source of the whole game page, so source checks survive the split into parts. */
export function readGamePage(): string {
  return PARTS
    .map(parts => join(APP, ...parts))
    .filter(path => existsSync(path))
    .map(path => readFileSync(path, 'utf-8'))
    .join('\n')
}
