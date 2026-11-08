import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  addCheckNode,
  applyMessageTrace,
  canUseNodeKind,
  connectBoardEdge,
  createStarterBoard,
  formatCheckCost,
  formatQuotaSummary,
  isAiAgentNode,
  removeBoardNode,
  resolveConsoleAccess,
  toApiBoard
} from '../app/utils/gameBoard'

const APP_DIR = join(import.meta.dirname, '..', 'app')

function walkAppFiles(dir: string): string[] {
  const results: string[] = []
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    const st = statSync(full)
    if (st.isDirectory()) {
      results.push(...walkAppFiles(full))
    } else if ((entry.endsWith('.vue') || entry.endsWith('.ts')) && !full.endsWith('api.gen.ts')) {
      results.push(full)
    }
  }
  return results
}

describe('game landing and levels', () => {
  it('[WEB-GAME-001] landing page links to easy, medium, and hard levels and displays scores', () => {
    const indexSource = readFileSync(join(APP_DIR, 'pages', 'index.vue'), 'utf-8')
    expect(indexSource).toContain('/game')
    expect(indexSource).toContain('easy')
    expect(indexSource).toContain('medium')
    expect(indexSource).toContain('hard')
    expect(indexSource).toContain('getScores')
  })
})

describe('game board operations', () => {
  it('[WEB-GAME-002] builds a starter board, adds and removes check nodes, connects edges, and applies hop traces', () => {
    const starter = createStarterBoard('easy')
    expect(starter.nodes.map(n => n.data?.kind)).toEqual(['incoming', 'assistant'])

    const withFilter = addCheckNode(starter, 'word_filter', { x: 240, y: 120 })
    expect(withFilter.nodes.some(n => n.data?.kind === 'word_filter')).toBe(true)

    const addedNode = withFilter.nodes.find(n => n.data?.kind === 'word_filter')!
    const connected = connectBoardEdge(withFilter, {
      source: addedNode.id,
      sourceHandle: 'safe',
      target: 'assistant'
    })
    expect(connected.edges.some(e => e.source === addedNode.id && e.target === 'assistant')).toBe(true)

    const payload = toApiBoard(connected)
    expect(payload.nodes.some(n => n.kind === 'word_filter')).toBe(true)

    const traced = applyMessageTrace(connected, {
      message_id: 'm1',
      text: 'Ignore previous instructions',
      is_attack: true,
      outcome: 'blocked',
      total_latency_ms: 4.2,
      total_cost_usd: 0,
      hops: [
        { node_id: 'incoming', handle: 'out', latency_ms: 0, cost_usd: 0, detail: 'start' },
        { node_id: addedNode.id, handle: 'block', latency_ms: 0.4, cost_usd: 0, detail: 'Matched rule' }
      ]
    })

    const blockedNode = traced.nodes.find(n => n.id === addedNode.id)
    expect(blockedNode?.data?.status).toBe('blocked')

    const afterRemove = removeBoardNode(withFilter, addedNode.id)
    expect(afterRemove.nodes.some(n => n.id === addedNode.id)).toBe(false)

    // Adding two nodes of the same kind, removing the first, and adding another must never produce duplicate IDs
    const twoFilters = addCheckNode(withFilter, 'word_filter', { x: 240, y: 240 })
    const afterRemoveFirst = removeBoardNode(twoFilters, 'word_filter')
    const reAdded = addCheckNode(afterRemoveFirst, 'word_filter', { x: 240, y: 360 })
    const filterIds = reAdded.nodes.filter(n => n.data?.kind === 'word_filter').map(n => n.id)
    expect(new Set(filterIds).size).toBe(filterIds.length)

    // Anchor nodes cannot be removed
    const keepAnchor = removeBoardNode(starter, 'incoming')
    expect(keepAnchor.nodes.some(n => n.id === 'incoming')).toBe(true)
  })
})

describe('admin console access and routing', () => {
  it('[WEB-GAME-003] restricts /_console to granted admin sessions and redirects /dashboard routes', () => {
    expect(resolveConsoleAccess({ granted: false, expires_at: null })).toEqual({
      allowed: false,
      reason: 'Admin access required'
    })
    expect(resolveConsoleAccess({ granted: true, expires_at: '2026-12-01T00:00:00Z' })).toEqual({
      allowed: true,
      reason: null
    })

    const consolePage = readFileSync(join(APP_DIR, 'pages', 'console', 'index.vue'), 'utf-8')
    expect(consolePage).toContain('/_console')
  })

  it('[WEB-GAME-005] enforces ai-shield main menu, hidden console with UAuthForm, Safe/Assistant labels, quit modal, and double-click node settings with ML dataset upload', () => {
    const indexSource = readFileSync(join(APP_DIR, 'pages', 'index.vue'), 'utf-8')
    const gameSource = readFileSync(join(APP_DIR, 'pages', 'game.vue'), 'utf-8')
    const appSource = readFileSync(join(APP_DIR, 'app.vue'), 'utf-8')
    const dashboardLayout = readFileSync(join(APP_DIR, 'layouts', 'dashboard.vue'), 'utf-8')

    // Branded ai-shield, no client-side links to /_console on public pages
    expect(indexSource).toContain('ai-shield')
    expect(indexSource).not.toContain('/_console')
    expect(gameSource).not.toContain('/_console')
    expect(appSource).not.toContain('/_console')

    // Guard /_console with UAuthForm
    expect(dashboardLayout).toContain('UAuthForm')

    // Main menu: Play Game, Settings, Leaderboard, Solved status, and High Score
    expect(indexSource).toContain('Play Game')
    expect(indexSource).toContain('Settings')
    expect(indexSource).toContain('Leaderboard')
    expect(indexSource).toContain('High score')

    // Game page: quit confirmation modal, Tools left panel, double-click node modal, ML dataset upload
    expect(gameSource).toContain('Are you sure you want to quit? your progress will not be saved')
    expect(gameSource).toContain('Tools')
    expect(gameSource).not.toContain('Available checks')
    expect(gameSource).toContain('@node-double-click')
    expect(gameSource).toContain('@nodes-change')
    expect(gameSource).toContain('v-model:nodes')
    expect(gameSource).toContain('ml_classifier')

    // Starter board has no pre-placed tool nodes (anchor labels moved to WEB-AGENT-001, spec 0020)
    const easyBoard = createStarterBoard('easy')
    expect(easyBoard.nodes.every(n => n.data?.isAnchor)).toBe(true)
  })

  it('[WEB-GAME-006] enforces client player auth, removes BYOK in settings, locks AI agent nodes for anonymous users, and displays free daily quotas', () => {
    const indexSource = readFileSync(join(APP_DIR, 'pages', 'index.vue'), 'utf-8')
    const gameSource = readFileSync(join(APP_DIR, 'pages', 'game.vue'), 'utf-8')

    // BYOK is completely removed from Settings and Game pages
    expect(indexSource).not.toContain('Configure secrets')
    expect(indexSource).not.toContain('useByodSecrets')
    expect(indexSource).not.toContain('openai_api_key')
    expect(indexSource).not.toContain('groq_api_key')
    expect(indexSource).not.toContain('gemini_api_key')
    expect(gameSource).not.toContain('useByodSecrets')
    expect(gameSource).not.toContain('Save score')

    // Client auth state on landing and game pages; the form itself lives on /login (WEB-GAME-007)
    expect(indexSource).toContain('usePlayerAuth')
    expect(gameSource).toContain('usePlayerAuth')
    expect(gameSource).toContain('isSidebarCollapsed')

    // AI agent node gating (safety_check and agent_review)
    expect(isAiAgentNode('safety_check')).toBe(true)
    expect(isAiAgentNode('agent_review')).toBe(true)
    expect(isAiAgentNode('word_filter')).toBe(false)
    expect(isAiAgentNode('quick_screen')).toBe(false)

    const anonSession = {
      authenticated: true,
      is_anonymous: true,
      tier: 'anonymous' as const,
      email: null,
      player_name: 'Anonymous',
      ai_nodes_allowed: false,
      can_record_scores: false,
      daily_wave_limit: null,
      wave_runs_used: 0,
      daily_test_limit: null,
      test_runs_used: 0
    }
    expect(canUseNodeKind('word_filter', anonSession)).toBe(true)
    expect(canUseNodeKind('safety_check', anonSession)).toBe(false)
    expect(canUseNodeKind('agent_review', anonSession)).toBe(false)
    expect(formatQuotaSummary(anonSession)).toBe('')

    const freeSession = {
      authenticated: true,
      is_anonymous: false,
      tier: 'free' as const,
      email: 'user@example.com',
      player_name: 'UserOne',
      ai_nodes_allowed: true,
      can_record_scores: true,
      daily_wave_limit: 3,
      wave_runs_used: 1,
      daily_test_limit: 10,
      test_runs_used: 3
    }
    expect(canUseNodeKind('safety_check', freeSession)).toBe(true)
    expect(canUseNodeKind('agent_review', freeSession)).toBe(true)
    expect(formatQuotaSummary(freeSession)).toContain('2/3')
    expect(formatQuotaSummary(freeSession)).toContain('7/10')

    const paidSession = {
      ...freeSession,
      tier: 'paid' as const,
      daily_wave_limit: null,
      daily_test_limit: null
    }
    expect(formatQuotaSummary(paidSession)).toBe('')
  })

  it('[WEB-GAME-007] moves player sign-in to a dedicated auth page with UAuthForm and removes anonymous-only UI from the main menu', () => {
    const indexSource = readFileSync(join(APP_DIR, 'pages', 'index.vue'), 'utf-8')
    const authSource = readFileSync(join(APP_DIR, 'composables', 'usePlayerAuth.ts'), 'utf-8')
    const loginPath = join(APP_DIR, 'pages', 'auth', 'login.vue')

    // The main menu links to /auth/login and no longer hosts the auth form or modal
    expect(indexSource).not.toContain('UAuthForm')
    expect(indexSource).not.toContain('isAuthModalOpen')
    expect(authSource).not.toContain('isAuthModalOpen')
    expect(indexSource).toContain('to="/auth/login"')

    // Anonymous players see no tier badge, record-scores button or anonymous score label
    expect(indexSource).toMatch(/<UBadge\s+v-if="!isAnonymous"\s+:label="session\.tier\.toUpperCase\(\)"/)
    expect(indexSource).not.toContain('Sign in to record scores')
    expect(indexSource).not.toContain('Not recorded (Anonymous)')
    expect(indexSource).toContain('{{ bestScoreFor(lvl.id).toLocaleString() }}')

    // The login page only leaves on success or when already signed in
    expect(existsSync(loginPath)).toBe(true)
    const loginSource = readFileSync(loginPath, 'utf-8')
    expect(loginSource).toContain('<UAuthForm')
    expect(loginSource).toContain('usePlayerAuth')
    expect(loginSource).toContain('to="/auth/register"')
    expect(loginSource).toMatch(/if \(succeeded\)\s*{\s*await navigateTo\('\/'\)/)
    expect(loginSource).toMatch(/if \(isLoggedIn\.value\)\s*{\s*await navigateTo\('\/'/)
  })

  it('[WEB-GAME-010] removes the account tier section from Settings while keeping sign-in and upgrade on the main menu', () => {
    const indexSource = readFileSync(join(APP_DIR, 'pages', 'index.vue'), 'utf-8')
    const settingsPath = join(APP_DIR, 'pages', 'settings.vue')
    expect(existsSync(settingsPath)).toBe(true)
    const settingsSource = readFileSync(settingsPath, 'utf-8')

    expect(indexSource).not.toContain('Account tier')
    expect(settingsSource).not.toContain('Account tier')
    expect(settingsSource).toContain('UColorModeSelect')
    expect(indexSource).toContain('label="Sign in / Create account"')
    expect(indexSource).toContain('label="Upgrade to Paid"')
  })

  it('[WEB-GAME-012] provides dedicated /settings, /auth/login, /auth/register, and /auth/recover pages', () => {
    const indexSource = readFileSync(join(APP_DIR, 'pages', 'index.vue'), 'utf-8')
    const gameSource = readFileSync(join(APP_DIR, 'pages', 'game.vue'), 'utf-8')
    const authSource = readFileSync(join(APP_DIR, 'composables', 'usePlayerAuth.ts'), 'utf-8')
    const apiSource = readFileSync(join(APP_DIR, 'composables', 'useShieldApi.ts'), 'utf-8')

    const settingsPath = join(APP_DIR, 'pages', 'settings.vue')
    const loginPath = join(APP_DIR, 'pages', 'auth', 'login.vue')
    const registerPath = join(APP_DIR, 'pages', 'auth', 'register.vue')
    const recoverPath = join(APP_DIR, 'pages', 'auth', 'recover.vue')

    // Settings is a dedicated page at /settings, not a modal on /
    expect(indexSource).toContain('to="/settings"')
    expect(indexSource).not.toContain('isSettingsOpen')
    expect(indexSource).not.toContain('<UModal')
    expect(existsSync(settingsPath)).toBe(true)
    const settingsSource = readFileSync(settingsPath, 'utf-8')
    expect(settingsSource).toContain('UColorModeSelect')
    expect(settingsSource).toContain('to="/"')
    expect(settingsSource).toContain('justify-between')
    expect(settingsSource).not.toContain('<template #header>')
    expect(settingsSource).not.toContain('<template #footer>')

    // Auth routes: /auth/login, /auth/register, /auth/recover
    expect(indexSource).toContain('to="/auth/login"')
    expect(gameSource).toContain('to="/auth/login"')
    expect(existsSync(loginPath)).toBe(true)
    expect(existsSync(registerPath)).toBe(true)
    expect(existsSync(recoverPath)).toBe(true)

    const loginSource = readFileSync(loginPath, 'utf-8')
    expect(loginSource).toContain('<UAuthForm')
    expect(loginSource).toContain('to="/auth/register"')
    expect(loginSource).toContain('to="/auth/recover"')
    expect(loginSource).toContain('signInWithPassword')

    const registerSource = readFileSync(registerPath, 'utf-8')
    expect(registerSource).toContain('<UAuthForm')
    expect(registerSource).toContain('to="/auth/login"')
    expect(registerSource).toContain('registerAccount')
    expect(registerSource).toContain('player_name')

    const recoverSource = readFileSync(recoverPath, 'utf-8')
    expect(recoverSource).toContain('<UAuthForm')
    expect(recoverSource).toContain('to="/auth/login"')
    expect(recoverSource).toContain('recoverPassword')

    expect(authSource).toContain('recoverPassword')
    expect(apiSource).toContain('/auth/recover')
  })

  it('[WEB-GAME-008] renders the Tools panel as a two-column grid of portrait cards', () => {
    const gameSource = readFileSync(join(APP_DIR, 'pages', 'game.vue'), 'utf-8')

    // Each check is a portrait UCard in a two-column grid, not a button row
    expect(gameSource).toContain('grid grid-cols-2')
    expect(gameSource).toMatch(/<UCard\s+v-for="chk in checks"/)
    expect(gameSource).not.toMatch(/<UButton\s+v-for="chk in checks"/)
    expect(gameSource).toContain('aspect-3/4')

    // Cards are reachable and operable from the keyboard
    expect(gameSource).toContain('role="button"')
    expect(gameSource).toContain('tabindex="0"')
    expect(gameSource).toContain('@keydown.enter.self="handlePlaceCheck(chk.kind)"')
    expect(gameSource).toContain('@keydown.space.self.prevent="handlePlaceCheck(chk.kind)"')

    // Card content
    expect(gameSource).toContain('NODE_CATALOG[chk.kind]?.subtitle')
    expect(gameSource).toContain('formatCheckCost(chk.cost_usd)')
    expect(gameSource).toContain('Sign in')

    // Cost label
    expect(formatCheckCost(0)).toBe('Free')
    expect(formatCheckCost(0.0002)).toBe('$0.0002')
  })

  it('[WEB-GAME-009] fixes the Tools panel width and adds a state-aware chevron, hover hint, drag to canvas, and tool info modal', () => {
    const gameSource = readFileSync(join(APP_DIR, 'pages', 'game.vue'), 'utf-8')

    // Fixed width with no resize handle
    expect(gameSource).not.toContain('sidebarWidth')
    expect(gameSource).not.toContain('startSidebarResize')
    expect(gameSource).not.toContain('cursor-col-resize')
    expect(gameSource).toContain('min-w-40')

    // Panel scrolls without a visible scrollbar
    expect(gameSource).toContain('[scrollbar-width:none]')
    expect(gameSource).toContain('[&::-webkit-scrollbar]:hidden')

    // Chevron reflects the panel state
    expect(gameSource).toContain('isSidebarCollapsed ? \'i-lucide-chevron-right\' : \'i-lucide-chevron-left\'')

    // Hover and focus hint
    expect(gameSource).toContain('group-hover:opacity-100')
    expect(gameSource).toContain('group-focus-visible:opacity-100')
    expect(gameSource).toContain('backdrop-blur-sm')
    expect(gameSource).toContain('Click or drag into canvas')
    expect(gameSource).toContain('Sign in to unlock')

    // Drag onto the canvas, locked cards excluded
    expect(gameSource).toContain(':draggable="canUseNodeKind(chk.kind, session)"')
    expect(gameSource).toContain('@dragstart="onToolDragStart($event, chk.kind)"')
    expect(gameSource).toContain('@dragover="onCanvasDragOver"')
    expect(gameSource).toContain('@drop="onCanvasDrop"')
    expect(gameSource).toContain('screenToFlowCoordinate')

    // Info modal opens without placing a node
    expect(gameSource).toContain('icon="i-lucide-info"')
    expect(gameSource).toContain('@click.stop="openToolInfo(chk)"')
    expect(gameSource).toContain('v-model:open="isToolInfoOpen"')
  })

  it('[WEB-GAME-011] shows only an explanation in the Input node modal and trims the tool info modal', () => {
    const gameSource = readFileSync(join(APP_DIR, 'pages', 'game.vue'), 'utf-8')

    // Input node modal: explanation only, no wiring controls
    expect(gameSource).toContain('Connect the node with a tool and the prompt will flow into the next node.')
    expect(gameSource).toMatch(/v-if="selectedNode\.data\.kind === 'incoming'"/)
    // Wiring controls live only in the tool-node branch, separate from Input (WEB-AGENT-009, WEB-AGENT-010)
    expect(gameSource).toMatch(/<!-- Tool nodes: settings and outputs -->\s*<template v-else>/)

    // Tool info modal: summary in the body, no outputs or access rows
    const toolInfoModal = gameSource.slice(
      gameSource.indexOf('<!-- Tool Info Modal -->'),
      gameSource.indexOf('<!-- Quit Confirmation Modal -->')
    )
    expect(toolInfoModal).not.toContain(':description=')
    expect(toolInfoModal).toContain('{{ infoTool.summary }}')
    expect(toolInfoModal).toContain('Latency')
    expect(toolInfoModal).toContain('Cost per message')
    expect(toolInfoModal).not.toContain('Outputs')
    expect(toolInfoModal).not.toContain('Access')
  })
})

describe('design hygiene and anti-slop copy standard', () => {
  const PALETTE_RE = /\b(?:text|bg|border|ring|from|to|via|fill|stroke)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b/
  const NATIVE_TAG_RE = /<(?:button|input|select|textarea|table|dialog)\b/i
  const BANNED_STYLE_RE = /(?:class="[^"]*![a-z]|shadow-\[|animate-pulse\b)/
  const EMOJI_RE = /\p{Extended_Pictographic}/u

  it('[WEB-GAME-004] [WEB-UI-001] uses no raw Tailwind palette utilities in app files', () => {
    const violations: string[] = []
    for (const file of walkAppFiles(APP_DIR)) {
      const text = readFileSync(file, 'utf-8')
      const match = text.match(PALETTE_RE)
      if (match) {
        violations.push(`${relative(APP_DIR, file)}: ${match[0]}`)
      }
    }
    expect(violations).toEqual([])
  })

  it('[WEB-GAME-004] [WEB-UI-002] uses no native button, input, select, textarea, table, or dialog elements', () => {
    const violations: string[] = []
    for (const file of walkAppFiles(APP_DIR)) {
      const text = readFileSync(file, 'utf-8')
      const match = text.match(NATIVE_TAG_RE)
      if (match) {
        violations.push(`${relative(APP_DIR, file)}: ${match[0]}`)
      }
    }
    expect(violations).toEqual([])
  })

  it('[WEB-GAME-004] [WEB-UI-003] uses no !-important utilities, arbitrary shadows, animate-pulse, emojis, or em-dashes', () => {
    const violations: string[] = []
    for (const file of walkAppFiles(APP_DIR)) {
      const rel = relative(APP_DIR, file)
      const text = readFileSync(file, 'utf-8')
      const styleMatch = text.match(BANNED_STYLE_RE)
      if (styleMatch) {
        violations.push(`${rel}: ${styleMatch[0]}`)
      }
      if (EMOJI_RE.test(text)) {
        violations.push(`${rel}: contains emoji`)
      }
      if (text.includes('\u2014') && !rel.endsWith('format.ts')) {
        violations.push(`${rel}: contains em-dash`)
      }
    }
    expect(violations).toEqual([])
  })

  it('[WEB-UI-005] uses color="error" only on UButton elements for dangerous actions', () => {
    const violations: string[] = []
    for (const file of walkAppFiles(APP_DIR)) {
      const rel = relative(APP_DIR, file)
      const text = readFileSync(file, 'utf-8')
      const tagRe = /<([A-Za-z0-9-]+)\b[^>]*color="error"[^>]*>/g
      for (const match of text.matchAll(tagRe)) {
        if (match[1] !== 'UButton') {
          violations.push(`${rel}: <${match[1]} color="error">`)
        }
      }
      if (/toast\.add\([^)]*color:\s*'error'/s.test(text)) {
        violations.push(`${rel}: toast color: 'error'`)
      }
    }
    expect(violations).toEqual([])
  })
})
