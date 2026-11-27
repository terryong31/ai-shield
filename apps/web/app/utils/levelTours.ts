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
  body: 'Prompts start at Input and travel along your wires to the Help Desk. Anything that never reaches the Help Desk is blocked. Stop enough attacks without blocking real customers.'
}

const RUN_STEP: LevelTourStep = {
  target: '[data-tour="run-wave"]',
  title: 'Run the wave',
  body: 'Each run is scored, and your best run is kept. Open the results to see which kinds of prompt got through.',
  side: 'bottom'
}

// Easy 1 to 4 teach one set of tools each; level 5 is the exam and has no tour (WEB-LADDER-002).
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
      body: 'Some attacks hide their request at the end of a very long message. Add a length limit after the Word filter.',
      side: 'right'
    },
    {
      target: node('incoming'),
      title: 'Wire it up',
      body: 'Drag from the OUT dot on Input to your first check, then from each PASS dot to the next node, ending at the Help Desk.',
      side: 'bottom'
    },
    RUN_STEP
  ],
  'easy-2': [
    {
      target: null,
      title: 'Hidden attacks',
      body: 'Some attacks hide their words with invisible characters, Base64 or hex codes. Two new tools unpack and scan them.'
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
      body: 'Place it after the cleaner and add patterns. Patterns are regular expressions, so one pattern can match many spellings.',
      side: 'right'
    },
    {
      target: node('incoming'),
      title: 'Order matters',
      body: 'Wire Input to the Text cleaner, then the Secret scanner, then the Help Desk. The scanner sees hidden words only after the cleaner unpacks them.',
      side: 'bottom'
    },
    RUN_STEP
  ],
  'easy-3': [
    {
      target: null,
      title: 'Same words, different purpose',
      body: 'Developers ask honest questions with the same words that attackers use. A list of words blocks them both.'
    },
    {
      target: node('secret_scan'),
      title: 'Precise patterns',
      body: 'Place a Secret scanner and write patterns that need the action and the target together, such as a live key or another merchant\'s token.',
      side: 'bottom'
    },
    {
      target: node('assistant'),
      title: 'Check the twins',
      body: 'Wire the scanner to the Help Desk. After a run, open the results: blocked normal prompts mean a pattern is too wide.',
      side: 'left'
    },
    RUN_STEP
  ],
  'easy-4': [
    {
      target: null,
      title: 'Meet the ML filter',
      body: 'Instead of writing rules, you teach a model from examples. On this level only the ML filter is available, and it learns from at most 40 rows.'
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
      body: 'Double-click the node, paste CSV examples (text,label with 1 for attacks and 0 for safe prompts) and press Train model. Write rows unlike the briefing examples, so the model learns the idea and not the words.',
      side: 'bottom'
    },
    {
      target: node('ml_classifier'),
      title: 'Three outcomes',
      body: 'Low-risk prompts leave through PASS and high-risk ones are blocked. Prompts the model is unsure about leave through UNCLEAR: leave it unwired to stop them.',
      side: 'bottom'
    },
    RUN_STEP
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
