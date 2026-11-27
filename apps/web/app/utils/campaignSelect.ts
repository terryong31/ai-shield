import type {
  DifficultyCategory,
  GameLevelSchema,
  LevelConstraintsSchema,
  LevelId,
  LevelProgressItem,
  LevelTier,
  NodeKind,
  PlayerProgressResponse,
  PlayerSessionStatus
} from '~/types/api'

export interface DifficultyCategoryCardData {
  difficulty: DifficultyCategory
  slug: 'easy' | 'medium' | 'hard'
  indexLabel: string
  levelsCount: number
  title: string
  subtitle: string
  icon: string
  badgeColor: 'success' | 'warning' | 'error'
  locked: boolean
}

export interface LevelTileItem {
  id: LevelId
  order: number
  stageIndex: number
  stageNumber: string
  kicker: string
  title: string
  difficulty: DifficultyCategory
  stars: number
  won: boolean
  mastered: boolean
  bestScore: number
  locked: boolean
  newIdea: string
  level: GameLevelSchema
}

export const CAMPAIGN_DIFFICULTY_COUNTS: Record<DifficultyCategory, number> = {
  Easy: 5,
  Medium: 7,
  Hard: 7
}

export const MAX_STARS_PER_LEVEL = 3

export const LEADERBOARD_DIFFICULTY_TABS: readonly DifficultyCategory[] = [
  'Easy',
  'Medium',
  'Hard'
] as const

export const BRIEFING_MODAL_MAX_WIDTH = 'sm:max-w-md'

export function formatNodeCountBadge(placed: number, max: number): string {
  return `${placed} / ${max} nodes`
}

export function difficultyBadgeColor(difficulty: DifficultyCategory): 'success' | 'warning' | 'error' {
  if (difficulty === 'Easy') return 'success'
  if (difficulty === 'Medium') return 'warning'
  return 'error'
}

export function toolRoleBadge(tool: {
  allowed: boolean
  dual_use?: boolean
}): { label: 'Safe' | 'Dual-Use' | 'Restricted', color: 'neutral' | 'warning' | 'error' } {
  if (tool.dual_use) {
    return { label: 'Dual-Use', color: 'warning' }
  }
  if (tool.allowed) {
    return { label: 'Safe', color: 'neutral' }
  }
  return { label: 'Restricted', color: 'error' }
}

export function canAccessLevel(
  level: Pick<GameLevelSchema, 'tier'>,
  session: Pick<PlayerSessionStatus, 'tier'>
): 'available' | 'pro_locked' {
  if (level.tier === 'free' || session.tier === 'paid') {
    return 'available'
  }
  return 'pro_locked'
}

export function canAccessDifficulty(
  difficulty: DifficultyCategory,
  session: Pick<PlayerSessionStatus, 'tier'>
): 'available' | 'pro_locked' {
  if (difficulty === 'Hard' && session.tier !== 'paid') {
    return 'pro_locked'
  }
  return 'available'
}

export function calculateLevelStars(
  progress?: Pick<LevelProgressItem, 'won' | 'medal' | 'mastered'> | null
): number {
  if (!progress || !progress.won) return 0
  return 1 + (progress.medal === 'gold' ? 1 : 0) + (progress.mastered ? 1 : 0)
}

/** The player's stored best on a level, used to seed the game header's High Score. */
export function levelHighScore(
  progress: PlayerProgressResponse | null | undefined,
  levelId: string
): { score: number | null, stars: number } {
  const item = progress?.levels.find(level => level.level_id === levelId)
  if (!item || item.best_score <= 0) return { score: null, stars: 0 }
  return { score: item.best_score, stars: calculateLevelStars(item) }
}

export function buildCategorySummaries(
  levels: GameLevelSchema[],
  session: Pick<PlayerSessionStatus, 'tier'>
): DifficultyCategoryCardData[] {
  const source = levels.length > 0 ? levels : FALLBACK_CAMPAIGN_LEVELS
  const countFor = (diff: DifficultyCategory, fallback: number) =>
    source.filter(l => l.difficulty === diff).length || fallback

  const easyCount = countFor('Easy', 5)
  const mediumCount = countFor('Medium', 10)
  const hardCount = countFor('Hard', 8)

  return [
    {
      difficulty: 'Easy',
      slug: 'easy',
      indexLabel: `${easyCount} Levels`,
      levelsCount: easyCount,
      title: 'Easy',
      subtitle: 'Firewall basics. No AI agent.',
      icon: 'i-lucide-shield-check',
      badgeColor: difficultyBadgeColor('Easy'),
      locked: false
    },
    {
      difficulty: 'Medium',
      slug: 'medium',
      indexLabel: `${mediumCount} Levels`,
      levelsCount: mediumCount,
      title: 'Medium',
      subtitle: 'LangGraph agent & dual-use tools.',
      icon: 'i-lucide-workflow',
      badgeColor: difficultyBadgeColor('Medium'),
      locked: false
    },
    {
      difficulty: 'Hard',
      slug: 'hard',
      indexLabel: `${hardCount} Levels`,
      levelsCount: hardCount,
      title: 'Hard',
      subtitle: 'Gullible agent & strict constraints.',
      icon: 'i-lucide-shield-alert',
      badgeColor: difficultyBadgeColor('Hard'),
      locked: canAccessDifficulty('Hard', session) === 'pro_locked'
    }
  ]
}

export function buildLevelTiles(
  levels: GameLevelSchema[],
  progressByLevel: Record<string, LevelProgressItem>,
  difficulty: DifficultyCategory,
  session: Pick<PlayerSessionStatus, 'tier'>
): LevelTileItem[] {
  const source = levels.length > 0 ? levels : FALLBACK_CAMPAIGN_LEVELS
  const filtered = source
    .filter(l => l.difficulty === difficulty)
    .sort((a, b) => a.order - b.order)

  return filtered.map((lvl, index) => {
    const stageIndex = index + 1
    const stageNumber = String(stageIndex).padStart(2, '0')
    const progress = progressByLevel[lvl.id]
    const won = Boolean(progress?.won)
    const mastered = Boolean(progress?.mastered)
    const bestScore = progress?.best_score ?? 0
    return {
      id: lvl.id,
      order: lvl.order,
      stageIndex,
      stageNumber,
      kicker: `Level ${stageNumber}`,
      title: lvl.title,
      difficulty: lvl.difficulty,
      stars: calculateLevelStars(progress),
      won,
      mastered,
      bestScore,
      locked: canAccessLevel(lvl, session) === 'pro_locked',
      newIdea: lvl.new_idea || lvl.summary,
      level: lvl
    }
  })
}

export function isCheckDisabledByConstraints(
  kind: NodeKind,
  constraints?: LevelConstraintsSchema | null
): boolean {
  if (!constraints) return false
  if (constraints.disabled_checks && constraints.disabled_checks.includes(kind)) {
    return true
  }
  return false
}

export function describeLevelConstraints(
  constraints?: LevelConstraintsSchema | null,
  checkLabels?: Record<string, string>
): string[] {
  if (!constraints) return []
  const items: string[] = []
  const labelFor = (kind: string) => checkLabels?.[kind] ?? kind.replace(/_/g, ' ')

  if (typeof constraints.max_check_nodes === 'number') {
    items.push(`Max ${constraints.max_check_nodes} check node${constraints.max_check_nodes === 1 ? '' : 's'}`)
  }
  if (constraints.disabled_checks && constraints.disabled_checks.length > 0) {
    items.push(`Disabled checks: ${constraints.disabled_checks.map(labelFor).join(', ')}`)
  }
  if (typeof constraints.max_avg_latency_ms === 'number') {
    items.push(`Hard latency limit: ${constraints.max_avg_latency_ms} ms avg`)
  }
  if (typeof constraints.max_total_cost_usd === 'number') {
    items.push(`Hard cost budget: $${constraints.max_total_cost_usd.toFixed(4)} total`)
  }
  if (typeof constraints.max_tokens === 'number') {
    items.push(`Hard token budget: ${constraints.max_tokens} tokens`)
  }
  return items
}

/** What each of the three stars needs (WEB-LADDER-001): clear, gold, then the mastery goal. */
export function starCriteria(level: GameLevelSchema): Array<{ label: string, goal: string }> {
  return [
    { label: 'First star', goal: 'Clear the level.' },
    { label: 'Second star', goal: 'Score 9,250 or more.' },
    { label: 'Third star', goal: level.follow_up?.description ?? 'Clear it and meet the mastery goal.' }
  ]
}

export function countPlacedCheckNodes(
  nodes: Array<{ data?: { isAnchor?: boolean } | null }>
): number {
  return nodes.filter(n => !n.data?.isAnchor).length
}

export function nextCampaignLevel(
  levels: GameLevelSchema[],
  currentLevelId: string
): GameLevelSchema | null {
  const source = levels.length > 0 ? levels : FALLBACK_CAMPAIGN_LEVELS
  const sorted = [...source].sort((a, b) => a.order - b.order)
  const idx = sorted.findIndex(l => l.id === currentLevelId)
  if (idx === -1 || idx + 1 >= sorted.length) return null
  return sorted[idx + 1] ?? null
}

function makeFallbackLevel(
  id: LevelId,
  order: number,
  difficulty: DifficultyCategory,
  tier: LevelTier,
  title: string,
  summary: string,
  protectedAsset: string,
  tags: string[],
  constraints: LevelConstraintsSchema = {},
  followUpDescription = 'Complete this level within the mastery efficiency target.',
  maxLatencyMs?: number,
  maxCostUsd?: number
): GameLevelSchema {
  const isEasy = difficulty === 'Easy'
  return {
    id,
    order,
    difficulty,
    tier,
    title,
    summary,
    new_idea: summary,
    briefing: [],
    version: 1,
    protected_asset: protectedAsset,
    max_latency_ms: maxLatencyMs ?? (isEasy ? 2500 : 3000),
    max_cost_usd: maxCostUsd ?? (isEasy ? 0.01 : difficulty === 'Medium' ? 0.025 : 0.03),
    tags,
    constraints,
    follow_up: {
      description: followUpDescription
    },
    messages: [],
    agent: isEasy ? null : { objective: summary, tools: [], token_budget: 1400 },
    agent_tier: isEasy ? null : difficulty === 'Medium' ? 'standard' : 'budget',
    final_node_label: isEasy ? 'Help Desk' : 'Protected Agent'
  }
}

export const FALLBACK_CAMPAIGN_LEVELS: GameLevelSchema[] = [
  makeFallbackLevel('easy-1', 1, 'Easy', 'free', 'Public Helpdesk', 'Match attack phrases, and limit the length.', 'Store discount codes and admin login', [], { disabled_checks: ['text_cleanup', 'secret_scan', 'ml_classifier', 'jev', 'safety_check', 'llm_review', 'tool_filter'] }, 'Clear it with 2 check nodes or fewer.'),
  makeFallbackLevel('easy-2', 2, 'Easy', 'free', 'Hidden in Plain Sight', 'Clean the text before you scan it. Normal prompts also hold encoded text.', 'Store discount codes and admin login', [], { disabled_checks: ['ml_classifier', 'jev', 'safety_check', 'llm_review', 'tool_filter'] }, 'Clear it with 2 check nodes or fewer.'),
  makeFallbackLevel('easy-3', 3, 'Easy', 'free', 'Developer Docs Trap', 'The same words, for a different purpose.', 'Live keys and the orders database', [], { max_check_nodes: 3, disabled_checks: ['ml_classifier', 'jev', 'safety_check', 'llm_review', 'tool_filter'] }, 'Clear it with no word filter.'),
  makeFallbackLevel('easy-4', 4, 'Easy', 'pro', 'Train Your First Guard', 'Generalise from examples: train the ML filter.', 'Customer contact list and staff logins', [], { disabled_checks: ['word_filter', 'text_cleanup', 'length_limit', 'secret_scan', 'jev', 'safety_check', 'llm_review', 'tool_filter'] }, 'Stop all 12 attacks.'),
  makeFallbackLevel('easy-5', 5, 'Easy', 'pro', 'Noisy Gateway', 'Exam: every tool, two nodes, and 6 ms a prompt. Choose what matters.', 'Everything from levels 1 to 4', [], { max_check_nodes: 2, max_avg_latency_ms: 6.0 }, 'A perfect wave: every attack stopped and every normal prompt helped.'),
  makeFallbackLevel('medium-1', 6, 'Medium', 'free', 'HR Handbook', 'Agent rules, and a restricted tool.', 'Staff salary records', [], { disabled_checks: ['jev', 'safety_check', 'llm_review', 'ml_classifier'] }, 'Clear it with no word filter.'),
  makeFallbackLevel('medium-2', 7, 'Medium', 'free', 'Refund Bot', 'Do half of a mixed request: run the safe part, skip the forbidden part.', 'Refunds to customers\' cards', [], { max_check_nodes: 4 }, 'Clear it with no LLM review.'),
  makeFallbackLevel('medium-3', 8, 'Medium', 'pro', 'Poisoned Inbox', 'Quoted text is data, never a task.', 'Client email threads', [], { max_check_nodes: 4 }, 'Clear it with 3 check nodes or fewer.'),
  makeFallbackLevel('medium-4', 9, 'Medium', 'pro', 'Lost in Translation', 'Meaning, not words, in four languages.', 'Patient records', [], { disabled_checks: ['word_filter', 'secret_scan'] }, 'Clear it with a list cost of $0.00080 or less.'),
  makeFallbackLevel('medium-5', 10, 'Medium', 'pro', 'Express Lane', 'Send only the Unclear prompts to paid checks.', 'Customer money', [], { max_total_cost_usd: 0.0008 }, 'Clear it with a list cost of $0.00050 or less.'),
  makeFallbackLevel('medium-6', 11, 'Medium', 'pro', 'Dual-Use Refund Desk', 'One tool, right or wrong by context.', 'Store credit and customer data', [], { max_check_nodes: 5 }, 'Clear it with no LLM review.'),
  makeFallbackLevel('medium-7', 12, 'Medium', 'pro', 'CRM Boss', 'Capstone: combine levels 6 to 11.', 'Customer accounts and the CRM', [], { max_check_nodes: 5, max_total_cost_usd: 0.004 }, 'Clear it with 4 check nodes or fewer.'),
  makeFallbackLevel('hard-1', 13, 'Hard', 'pro', 'Warehouse', 'The eager agent does what it is told: plausible abuse gets through.', 'Stock, shipments and supplier data', [], { max_check_nodes: 5 }, 'Clear it with 4 check nodes or fewer.'),
  makeFallbackLevel('hard-2', 14, 'Hard', 'pro', 'No Heavy Weapons', 'Stop plausible abuse without the LLM review.', 'Card limits, fraud alerts and payments', [], { max_check_nodes: 3, disabled_checks: ['llm_review'] }, 'Clear it with no safety check.'),
  makeFallbackLevel('hard-3', 15, 'Hard', 'pro', 'Auditor\'s Minefield', 'Honest staff quote attack text: the words of an attack are in normal prompts too.', 'Contracts and the audit log', [], { disabled_checks: ['word_filter'] }, 'Clear it with a list cost of $0.00120 or less.'),
  makeFallbackLevel('hard-4', 16, 'Hard', 'pro', 'Polyglot', 'Two layers of encoding: a language inside an encoding, or one encoding inside another.', 'Cargo routes and invoices', [], { max_check_nodes: 5 }, 'Clear it with 4 check nodes or fewer.'),
  makeFallbackLevel('hard-5', 17, 'Hard', 'pro', 'Finance Desk', 'Decide by amount and proof.', 'Expense approvals and vendor bank details', [], { max_check_nodes: 5 }, 'Clear it with a list cost of $0.00100 or less.'),
  makeFallbackLevel('hard-6', 18, 'Hard', 'pro', 'Cloud Ops', 'Two dual-use tools with opposite conditions.', 'Production servers and the on-call team', [], { max_check_nodes: 5, disabled_checks: ['safety_check'] }, 'Clear it with 4 check nodes or fewer.'),
  makeFallbackLevel('hard-7', 19, 'Hard', 'pro', 'Zero-Day', 'Final capstone: combine levels 13 to 18.', 'Payouts, admin roles and customer data', [], { max_check_nodes: 6, max_total_cost_usd: 0.004 }, 'Clear it with 5 check nodes or fewer.')
]
