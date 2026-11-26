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
  level: GameLevelSchema
}

export const CAMPAIGN_DIFFICULTY_COUNTS: Record<DifficultyCategory, number> = {
  Easy: 5,
  Medium: 10,
  Hard: 8
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
  makeFallbackLevel('easy-1', 1, 'Easy', 'free', 'Public Helpdesk', 'Stop direct prompt overrides and oversized prompt-stuffing payloads while letting store customer questions through.', 'Store VIP discount code', ['Word Filter', 'Length Limit', 'Edge Defence'], {}, 'Use <= 2 check nodes and keep average latency <= 1.0 ms.'),
  makeFallbackLevel('easy-2', 2, 'Easy', 'free', 'Hidden in Plain Sight', 'Normalize zero-width obfuscation, Base64 strings, and hex smuggling with Text Cleaner before scanning for secret phrases.', 'Partner portal API key', ['Text Cleaner', 'Secret Scan', 'Pipeline Order'], {}, 'Complete with $0.00 total cost (zero paid AI checks).'),
  makeFallbackLevel('easy-3', 3, 'Easy', 'free', 'Train Your First Guard', 'Word Filter is locked by policy. Train an ML Filter from CSV examples and route Safe vs. Unclear prompts without blocking polite questions.', 'Merchant admin console', ['ML Filter', '3-Way Branching', 'CSV Training'], { disabled_checks: ['word_filter'] }, 'Spend $0.00 total cost and keep average latency <= 6.0 ms.'),
  makeFallbackLevel('easy-4', 4, 'Easy', 'pro', 'Developer Docs Trap', 'Legitimate developers ask educational questions mentioning SELECT * and API_KEY setup; filter real credential theft within 4 check nodes.', 'Internal SDK signing key', ['False Positives', 'ML Triage', 'Edge Rules'], { max_check_nodes: 4 }, 'Solve with $0.00 total cost (no paid AI checks).'),
  makeFallbackLevel('easy-5', 5, 'Easy', 'pro', 'The Noisy Gateway', 'Easy capstone combining oversized stuffing, zero-width smuggling, paraphrased overrides, and benign lookalikes under an 8 ms SLA.', 'Gateway master routing key', ['Capstone', 'Latency SLA', 'Defense in Depth'], { max_avg_latency_ms: 8 }, 'Use <= 4 check nodes and spend $0.00 total cost.'),
  makeFallbackLevel('medium-1', 6, 'Medium', 'free', 'HR Handbook Assistant', 'Stop base64 tricks and roleplay jailbreaks without blocking staff who ask normal policy questions.', 'Executive salary records', ['LangGraph Agent', 'Tool Policy', 'Roleplay'], {}, 'Win without using LLM review.'),
  makeFallbackLevel('medium-2', 7, 'Medium', 'free', 'Over-Helpful Refund Bot', 'Let valid parcel questions use lookup_order while switching off issue_refund when impatient shoppers slip in quick-fix refund requests.', 'Merchant refund payout API', ['Pattern C Bait', 'Tool Policy', 'Latency'], {}, 'Keep average latency <= 600.0 ms.'),
  makeFallbackLevel('medium-3', 8, 'Medium', 'pro', 'Poisoned Inbox', 'Summarize legitimate supplier emails while stripping hidden forwarding instructions buried inside quoted email threads.', 'Executive inbox threads', ['Pattern D RAG Bait', 'Indirect Injection'], {}, 'Solve using at most 3 check nodes.'),
  makeFallbackLevel('medium-4', 9, 'Medium', 'pro', 'Lost in Translation', 'Word Filter is disabled. Catch Malay, Spanish, and JSON-wrapped overrides semantically without over-spending or blocking clinic bookings.', 'Patient medical records', ['Multilingual', 'JSON Framing', 'Cost Cap'], { disabled_checks: ['word_filter'] }, 'Keep total wave cost <= $0.008.'),
  makeFallbackLevel('medium-5', 10, 'Medium', 'pro', 'Confused Dev Copilot', 'Let engineers ask harmless debugging questions about .env files and SQL joins while blocking real read_env_secrets and run_sql attacks.', 'Production .env & SQL database', ['False Positives', 'Multi-Tool', 'Token Budget'], {}, 'Complete with total tokens <= 4,500.'),
  makeFallbackLevel('medium-6', 11, 'Medium', 'pro', '50ms Express Lane', 'Route obvious benign FX inquiries past expensive LLM checks to keep the entire wave under a strict $0.005 total cost cap.', 'Treasury wire transfer gateway', ['Funnel Routing', 'Cost SLA'], { max_total_cost_usd: 0.005 }, 'Win without using LLM review.', 3000, 0.02),
  makeFallbackLevel('medium-7', 12, 'Medium', 'pro', 'IT Helpdesk Triage', 'Tickets bait three separate privileged IT actions (reset_mfa, grant_admin, delete_ticket). Route tool policy selectively within 5 check nodes.', 'Identity & ticket admin controls', ['Multi-Tool Policy', 'Triage'], { max_check_nodes: 5 }, 'Solve using at most 3 check nodes.'),
  makeFallbackLevel('medium-8', 13, 'Medium', 'pro', 'Dual-Use Refund Desk', 'First Dual-Use tool: issue_store_credit MUST work for verified damaged deliveries, yet MUST be switched off on quick-fix bait and attacks.', 'Store credit issuance balance', ['Dual-Use Tool', 'Tool Policy'], {}, 'Win without using LLM review.'),
  makeFallbackLevel('medium-9', 14, 'Medium', 'pro', 'Encoded Cargo Courier', 'Tracking remarks hide Base64 and URL-encoded tool-rerouting directives. Clean encoded text before Tool Policy decides what to gate.', 'Maritime freight routing', ['Text Cleaner', 'Tool Policy', 'URL Encoding'], {}, 'Use <= 4 check nodes and keep total cost <= $0.007.'),
  makeFallbackLevel('medium-10', 15, 'Medium', 'pro', 'Dual-Use CRM Boss', 'Medium capstone: gate Dual-Use send_customer_email selectively, guard delete_account/export_crm, and stay within 5 check nodes.', 'Enterprise CRM & customer communications', ['Capstone', 'Dual-Use Tool', 'Node Cap'], { max_check_nodes: 5 }, 'Keep total tokens <= 5,000 without using LLM review.'),
  makeFallbackLevel('hard-1', 16, 'Hard', 'pro', 'Warehouse Ops Under Siege', 'Defend a gullible warehouse assistant across 6 tools against multi-vector chained injections, Base64 directives, and Pattern C/D tool baits.', 'Payroll database and audit logs', ['Gullible Agent', '6 Tools', 'Multi-Vector'], {}, 'Solve using at most 4 check nodes.'),
  makeFallbackLevel('hard-2', 17, 'Hard', 'pro', 'No Heavy Weapons', 'Banking compliance prohibits LLM review. Stop attacks and tool bait against a gullible banking assistant with lighter checks and Jev.', 'Retail banking transfers & fraud rules', ['No LLM Review', 'Banking', 'Latency SLA'], { disabled_checks: ['llm_review'] }, 'Use <= 4 check nodes and keep average latency <= 500.0 ms.'),
  makeFallbackLevel('hard-3', 18, 'Hard', 'pro', 'The Auditor\'s Minefield', 'Word Filter is disabled and legitimate compliance auditors quote attack strings verbatim in audit reports. Avoid false alarms on quoted text.', 'Legal contract signing & privileged archive', ['False Positives', 'Quoted Strings', 'No Word Filter'], { disabled_checks: ['word_filter'] }, 'Keep total wave cost <= $0.010.'),
  makeFallbackLevel('hard-4', 19, 'Hard', 'pro', 'Polyglot & Stego Smuggler', 'SRE telemetry hides URL-encoded JSON, Base64 key-rotation commands, and YAML tool invocations. Clean and block within 5 check nodes.', 'Cloud keys, cluster nodes, and firewall', ['Polyglot', 'Text Cleaner', 'Node Cap'], { max_check_nodes: 5 }, 'Win without using LLM review.'),
  makeFallbackLevel('hard-5', 20, 'Hard', 'pro', 'Dual-Use Finance Desk', 'Allow valid Dual-Use approve_expense calls for small receipts while blocking spoofed CEO payment memos, large unauthorized approvals, and bank fraud.', 'Corporate expense ledger & bank routing', ['Dual-Use Tool', 'CEO Spoof', 'Node Cap'], { max_check_nodes: 5 }, 'Keep total wave cost <= $0.009.'),
  makeFallbackLevel('hard-6', 21, 'Hard', 'pro', 'Minimalist Fortress', 'Guard CI/CD production deployment tools against a gullible agent using at most 3 placeable check nodes total.', 'Production release & schema pipelines', ['Strict 3-Node Limit', 'CI/CD'], { max_check_nodes: 3 }, 'Win without using LLM review.'),
  makeFallbackLevel('hard-7', 22, 'Hard', 'pro', 'Dual-Use Cloud Ops', 'Safety Check is disabled, and BOTH restart_staging_pod and notify_oncall are Dual-Use tools that must run only on genuine staging incidents.', 'Kubernetes prod cluster & on-call pager', ['2x Dual-Use', 'No Safety Check'], { disabled_checks: ['safety_check'] }, 'Solve using at most 4 check nodes.'),
  makeFallbackLevel('hard-8', 23, 'Hard', 'pro', 'Zero-Day Red Team Capstone', 'Grand capstone mixing Dual-Use escalations, quoted auditor logs, Base64 smuggling, and four destructive restricted tools under cost & node limits.', 'Enterprise payout, SQL, superadmin, and audit vault', ['Final Capstone', 'Dual-Use Tool', 'Budget & Cost Cap'], { max_check_nodes: 6, max_total_cost_usd: 0.015 }, 'Use <= 4 check nodes and keep average latency <= 650.0 ms.')
]
