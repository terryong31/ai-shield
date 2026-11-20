export type TourSide = 'top' | 'right' | 'bottom' | 'left'

export interface LevelTourStep {
  /** A `[data-tour="…"]` selector, or `null` for a centred step. */
  target: string | null
  title: string
  body: string
  side?: TourSide
}

const tool = (kind: string) => `[data-tour="tool-${kind}"]`
const node = (kind: string) => `[data-tour="node-${kind}"]`

const INTRO_STEP: LevelTourStep = {
  target: null,
  title: 'How a wave works',
  body: 'Prompts start at Input and travel along your wires to the Help Desk. Anything that never reaches the Help Desk is blocked. Stop every attack without blocking a real customer.'
}

const FINISH_STEPS: LevelTourStep[] = [
  {
    target: '[data-tour="test-bar"]',
    title: 'Try a message',
    body: 'Type any prompt and press Test to see the path it takes through your board.',
    side: 'bottom'
  },
  {
    target: '[data-tour="run-wave"]',
    title: 'Run the wave',
    body: 'When you are ready, send the whole wave. Stop every attack and let every customer through to win.',
    side: 'bottom'
  }
]

const LEVEL_TOURS: Record<string, LevelTourStep[]> = {
  'easy-1': [
    INTRO_STEP,
    {
      target: tool('word_filter'),
      title: 'Word filter',
      body: 'Click or drag it onto the board. Double-click the placed node and list phrases attackers use, such as "ignore previous".',
      side: 'right'
    },
    {
      target: tool('length_limit'),
      title: 'Length limit',
      body: 'Add it after the Word filter to block oversized prompt-stuffing messages.',
      side: 'right'
    },
    {
      target: node('incoming'),
      title: 'Wire it up',
      body: 'Drag from the OUT dot on Input to your first check, then from each PASS dot to the next node, ending at the Help Desk.',
      side: 'bottom'
    },
    ...FINISH_STEPS
  ],
  'easy-2': [
    {
      target: null,
      title: 'Hidden attacks',
      body: 'Some attacks hide their words with invisible characters, Base64 or hex codes. On this level only the Text cleaner and Secret scanner are available.'
    },
    {
      target: tool('text_cleanup'),
      title: 'Text cleaner',
      body: 'Place it first. Double-click it and switch on the transforms that unpack hidden text.',
      side: 'right'
    },
    {
      target: tool('secret_scan'),
      title: 'Secret scanner',
      body: 'Place it after the cleaner and add patterns such as secret or api_key. Patterns are regular expressions.',
      side: 'right'
    },
    {
      target: node('incoming'),
      title: 'Order matters',
      body: 'Wire Input to the Text cleaner, then the Secret scanner, then the Help Desk. The scanner only sees hidden words after the cleaner has unpacked them.',
      side: 'bottom'
    },
    ...FINISH_STEPS
  ],
  'easy-3': [
    {
      target: null,
      title: 'Meet the ML filter',
      body: 'Instead of writing rules, you teach a model from examples. On this level only the ML filter is available.'
    },
    {
      target: tool('ml_classifier'),
      title: 'Place the ML filter',
      body: 'Click or drag it onto the board.',
      side: 'right'
    },
    {
      target: node('ml_classifier'),
      title: 'Train it',
      body: 'Double-click the node, paste CSV examples (text,label with 1 for attacks and 0 for safe prompts) and press Train model. Until it is trained, it lets everything through.',
      side: 'bottom'
    },
    {
      target: node('ml_classifier'),
      title: 'Three outcomes',
      body: 'Low-risk prompts leave through PASS and high-risk ones are blocked. Prompts the model is unsure about leave through UNCLEAR: leave it unwired to stop them.',
      side: 'bottom'
    },
    {
      target: node('assistant'),
      title: 'Connect the Help Desk',
      body: 'Wire Input to the ML filter, then its PASS dot to the Help Desk.',
      side: 'left'
    },
    ...FINISH_STEPS
  ]
}

export function levelTourSteps(levelId: string): LevelTourStep[] {
  return LEVEL_TOURS[levelId] ?? []
}

export function tourSeenKey(levelId: string): string {
  return `ai-shield:tour-seen:${levelId}`
}

// Storage can be missing or blocked (private mode, SSR); the tour then shows again next time.
export function hasSeenTour(levelId: string, storage: Pick<Storage, 'getItem'> | undefined = globalThis.localStorage): boolean {
  try {
    return storage?.getItem(tourSeenKey(levelId)) === '1'
  } catch {
    return false
  }
}

export function markTourSeen(levelId: string, storage: Pick<Storage, 'setItem'> | undefined = globalThis.localStorage): void {
  try {
    storage?.setItem(tourSeenKey(levelId), '1')
  } catch {
    // Ignore: remembering the tour is a convenience.
  }
}
