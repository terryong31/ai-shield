<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch, type Ref } from 'vue'
import {
  VueFlow,
  useVueFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeMouseEvent
} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import GameNode from '~/components/workflow/GameNode.vue'
import {
  CUSTOM_LIMITS,
  DATASET_EXAMPLE,
  PROVIDER_OPTIONS,
  canRunCustom,
  customModeAccess,
  datasetRowsToCsv,
  parseDatasetCsv,
  validateCustomAgent,
  type CustomAgent,
  type ProviderId
} from '~/utils/customSandbox'
import type {
  CheckDefinitionSchema,
  GameLevelSchema,
  LevelId,
  MessageTraceSchema,
  NodeKind,
  WaveScoreSchema
} from '~/types/api'
import {
  AGENT_RULE_LIMIT,
  AGENT_RULE_MAX_CHARS,
  NODE_CATALOG,
  SAFETY_CHECK_MODELS,
  LLM_REVIEW_MODELS,
  DEFAULT_SAFETY_CHECK_MODEL,
  DEFAULT_LLM_REVIEW_MODEL,
  nodeSupportsThinking,
  addAgentRule,
  addCheckNode,
  agentRulesFrom,
  applyWaveSummary,
  canAddAgentRule,
  canUseNodeKind,
  nodeKeyRequirement,
  connectBoardEdge,
  createStarterBoard,
  formatCheckCost,
  formatToolName,
  FINAL_NODE_LABELS,
  isClassifyOnlyLevel,
  isValidLevelId,
  markBoardRunning,
  nodeCostLine,
  removeBoardNode,
  resetBoardStatuses,
  runsRemaining,
  attemptsLeftLabel,
  nextHighScore,
  isNewRecord,
  nextHighStars,
  scoreBreakdown,
  waveStars,
  waveOutcomeSummary,
  toApiBoard,
  boardFromSave,
  boardSignature,
  saveFromBoard,
  type GameNodeData,
  confusionMatrix,
  runWithAnonymousRetry
} from '~/utils/gameBoard'
import {
  FALLBACK_CAMPAIGN_LEVELS,
  canAccessLevel,
  levelHighScore,
  countPlacedCheckNodes,
  isCheckDisabledByConstraints,
  nextCampaignLevel
} from '~/utils/campaignSelect'
import { hasSeenTour, levelTourSteps, markTourSeen } from '~/utils/levelTours'
import {
  ML_TRAINING_NOTICE,
  REPLACE_MODEL_WARNING,
  applyTrainedModelToBoard,
  checkTrainingFile,
  decodeTrainingCsv,
  formatRemainingTrainings,
  markUntrainedModelNodes,
  needsReplaceConfirmation,
  triggerBeaconPurge
} from '~/utils/mlTraining'
import { TWITTER_CARD_ALT, TWITTER_CARD_PATH, resolveSiteUrl } from '~/utils/seo'

const route = useRoute()
const goBack = useGoBack()
const toast = useToast()
const { getLevels, runGame, trainClassifier, purgeModels, getSave, putSave, getProgress } = useShieldApi()
const {
  session,
  isAnonymous,
  isLoggedIn,
  isPaid,
  refreshSession,
  continueAnonymously
} = usePlayerAuth()
const { refreshScores } = useLeaderboard()
const { getCachedBoard, setCachedBoard } = useSavedBoardCache()

// Custom sandbox (spec 0022) reuses the agent-level UI; its run goes out as level "custom".
const isCustomMode = computed(() => route.query.level === 'custom')

const initialLevel = computed<LevelId>(() => {
  const q = String(route.query.level || 'easy-1')
  if (isValidLevelId(q)) return q
  if (q === 'custom') return 'medium-1'
  return 'easy-1'
})

const customAgent = ref<CustomAgent>({ objective: '', tools: [] })
const customProvider = ref<ProviderId>('openai')
const customModel = ref('')
// The player's API key: kept in this component's memory only, sent with each run.
const customApiKey = ref('')
const customDatasetText = ref(DATASET_EXAMPLE)
const customDataset = computed(() =>
  parseDatasetCsv(customDatasetText.value, customAgent.value.tools.map(t => t.name))
)
const customAgentErrors = computed(() => validateCustomAgent(customAgent.value))
const providerItems = PROVIDER_OPTIONS.map(p => ({ label: p.label, value: p.value }))

const addCustomTool = () => {
  if (customAgent.value.tools.length >= CUSTOM_LIMITS.tools) return
  customAgent.value.tools.push({ name: '', description: '', allowed: true })
}

const removeCustomTool = (index: number) => {
  customAgent.value.tools.splice(index, 1)
}

const onCustomDatasetFile = async (event: Event) => {
  const target = event.target as { files?: FileList | null } | null
  const file = target?.files?.[0]
  if (!file) return
  customDatasetText.value = await file.text()
}

const currentLevelId = ref<LevelId>(initialLevel.value)
const levels = ref<GameLevelSchema[]>(FALLBACK_CAMPAIGN_LEVELS)
const isBriefingOpen = ref(false)

const toolKinds: NodeKind[] = [
  'word_filter',
  'text_cleanup',
  'length_limit',
  'secret_scan',
  'ml_classifier',
  'jev',
  'safety_check',
  'llm_review'
]

const checks = ref<CheckDefinitionSchema[]>(
  toolKinds.map(kind => ({
    kind,
    label: NODE_CATALOG[kind].label,
    summary: NODE_CATALOG[kind].subtitle,
    handles: NODE_CATALOG[kind].handles,
    latency_ms: NODE_CATALOG[kind].latencyMs,
    cost_usd: NODE_CATALOG[kind].costUsd
  }))
)

const starter = createStarterBoard(currentLevelId.value)
const nodes = ref<Node<GameNodeData>[]>(starter.nodes) as Ref<Node<GameNodeData>[]>
const edges = ref<Edge[]>(starter.edges) as Ref<Edge[]>

const selectedNodeId = ref<string | null>(null)
const isNodeModalOpen = ref(false)
const isQuitModalOpen = ref(false)
const isSidebarCollapsed = ref(false)

const toolCardUi = {
  root: 'group relative flex aspect-3/4 min-w-40 flex-col select-none transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inverted',
  header: 'p-2 sm:px-2',
  body: 'flex min-h-0 flex-1 flex-col items-center justify-center gap-1.5 p-2 text-center sm:p-2',
  footer: 'p-2 sm:px-2'
}

const selectedNode = computed(() =>
  nodes.value.find(n => n.id === selectedNodeId.value) ?? null
)

const runningWave = ref(false)
const traces = ref<MessageTraceSchema[]>([])
const waveScore = ref<WaveScoreSchema | null>(null)
// Best wave score on this level this visit: kept across Restart, reset on level change.
const highScore = ref<number | null>(null)
const newRecord = ref(false)
// Stars of the high-score wave, always shown in the header (WEB-AGENT-019).
const highStars = ref(0)

const customMessage = ref('')

const customWordDraft = ref('')
const secretPatternDraft = ref('')
const jevKeyConfigured = ref(false)
const aiKeyConfigured = ref(false)
const nodeKeyState = computed(() => ({
  jevKeyAvailable: jevKeyConfigured.value,
  aiKeyAvailable: aiKeyConfigured.value
}))
const mlCsvDraft = ref('')
const mlTraining = ref(false)
const mlTrainStats = ref<{ sampleCount: number, accuracy: number } | null>(null)
const activeSessionModelId = ref<string | null>(null)
const isReplaceModelConfirmOpen = ref(false)

const mlAlgorithms = [
  { id: 'tfidf', label: 'TF-IDF' },
  { id: 'logistic_regression', label: 'Logistic Regression' },
  { id: 'linear_svm', label: 'Linear SVM' },
  { id: 'naive_bayes', label: 'Naive Bayes' },
  { id: 'random_forest', label: 'Random Forest' }
] as const
const mlAlgorithmItems = mlAlgorithms.map(alg => ({ label: alg.label, value: alg.id as string }))
const safetyCheckModelItems = SAFETY_CHECK_MODELS.map(m => ({ label: m.label, value: m.value as string }))
const llmReviewModelItems = LLM_REVIEW_MODELS.map(m => ({ label: m.label, value: m.value as string }))

const apiCustomAgent = computed(() => ({
  objective: customAgent.value.objective,
  tools: customAgent.value.tools.map(t => ({ ...t, dual_use: t.dual_use ?? false }))
}))

const currentLevel = computed<GameLevelSchema>(() => {
  if (isCustomMode.value) {
    return {
      id: 'medium-1',
      order: 6,
      tier: 'pro',
      title: 'Custom sandbox',
      difficulty: 'Medium',
      summary: 'Your own agent, dataset and model.',
      protected_asset: '',
      max_latency_ms: 3000,
      max_cost_usd: 0.002 * Math.max(1, customDataset.value.rows.length),
      messages: [],
      agent: { ...apiCustomAgent.value, token_budget: 0 },
      tags: ['Custom'],
      constraints: {},
      follow_up: null,
      agent_tier: null,
      final_node_label: 'Protected Agent'
    }
  }
  const found = levels.value.find(l => l.id === currentLevelId.value)
  if (found) return found
  const isEasy = currentLevelId.value.startsWith('easy-')
  const isMedium = currentLevelId.value.startsWith('medium-')
  return {
    id: currentLevelId.value,
    order: 1,
    tier: 'free',
    title: isEasy
      ? 'Public Helpdesk'
      : isMedium
        ? 'HR Handbook Assistant'
        : 'Warehouse Ops Under Siege',
    difficulty: isEasy ? 'Easy' : isMedium ? 'Medium' : 'Hard',
    summary: '',
    protected_asset: '',
    max_latency_ms: 3000,
    max_cost_usd: 0.025,
    messages: [],
    agent: isClassifyOnlyLevel(currentLevelId.value) ? null : { objective: '', tools: [], token_budget: 0 },
    tags: [],
    constraints: {},
    follow_up: null,
    agent_tier: isEasy ? null : isMedium ? 'standard' : 'budget',
    final_node_label: FINAL_NODE_LABELS[currentLevelId.value]
  }
})

const levelAgent = computed(() => currentLevel.value.agent)

const isProLevelLocked = computed(() =>
  !isCustomMode.value && canAccessLevel(currentLevel.value, session.value) === 'pro_locked'
)

const placedCheckNodeCount = computed(() => countPlacedCheckNodes(nodes.value))
const maxCheckNodes = computed(() => currentLevel.value.constraints?.max_check_nodes ?? null)
const nextLevel = computed(() =>
  isCustomMode.value ? null : nextCampaignLevel(levels.value, currentLevelId.value)
)
const runtimeConfig = useRuntimeConfig()
const siteUrl = computed(() => resolveSiteUrl(runtimeConfig.public.siteUrl))
const gameSeoDescription = computed(() =>
  currentLevel.value.summary
  || 'Build and test a layered prompt-injection defence workflow with word filters, ML classifiers, safety guardrails, and LLM reviewers on ai-shield.'
)

const gameSeoUrl = computed(() => {
  const q = route.query.level
  if (isValidLevelId(q)) {
    return `${siteUrl.value}/game?level=${q}`
  }
  return `${siteUrl.value}/game`
})

useSeoMeta({
  title: () => currentLevel.value.title,
  description: () => gameSeoDescription.value,
  ogTitle: () => `${currentLevel.value.title} | ai-shield`,
  ogDescription: () => gameSeoDescription.value,
  ogType: 'website',
  ogSiteName: 'ai-shield',
  ogUrl: () => gameSeoUrl.value,
  ogImage: () => `${siteUrl.value}${TWITTER_CARD_PATH}`,
  ogImageAlt: TWITTER_CARD_ALT,
  ogImageWidth: 1200,
  ogImageHeight: 630,
  twitterCard: 'summary_large_image',
  twitterTitle: () => `${currentLevel.value.title} | ai-shield`,
  twitterDescription: () => gameSeoDescription.value,
  twitterImage: () => `${siteUrl.value}${TWITTER_CARD_PATH}`,
  twitterImageAlt: TWITTER_CARD_ALT,
  robots: 'index, follow'
})

const FLOW_ID = 'shield-game-flow'
const { setNodes, setEdges, screenToFlowCoordinate } = useVueFlow(FLOW_ID)

const syncBoard = (next: { nodes: Node<GameNodeData>[], edges: Edge[] }) => {
  nodes.value = next.nodes
  edges.value = next.edges
  setNodes(next.nodes)
  setEdges(next.edges)
}

const onNodesChange = (changes: NodeChange[]) => {
  let currentNodes = nodes.value
  let currentEdges = edges.value
  let structureChanged = false

  for (const change of changes) {
    if (change.type === 'remove') {
      const updated = removeBoardNode({ nodes: currentNodes, edges: currentEdges }, change.id)
      if (updated.nodes.length !== currentNodes.length) {
        currentNodes = updated.nodes
        currentEdges = updated.edges
        structureChanged = true
        if (selectedNodeId.value === change.id) {
          selectedNodeId.value = null
          isNodeModalOpen.value = false
        }
      }
    } else if (change.type === 'position' && change.position) {
      const target = currentNodes.find(n => n.id === change.id)
      if (target) {
        target.position = { ...change.position }
      }
    }
  }

  if (structureChanged) {
    syncBoard({ nodes: currentNodes, edges: currentEdges })
  }
}

const onEdgesChange = (changes: EdgeChange[]) => {
  const removedIds = new Set<string>()
  for (const change of changes) {
    if (change.type === 'remove') {
      removedIds.add(change.id)
    }
  }
  if (removedIds.size > 0) {
    const nextEdges = edges.value.filter(e => !removedIds.has(e.id))
    if (nextEdges.length !== edges.value.length) {
      edges.value = nextEdges
      setEdges(nextEdges)
    }
  }
}

const resetBoard = () => {
  const fresh = createStarterBoard(currentLevelId.value)
  syncBoard(fresh)
  traces.value = []
  waveScore.value = null
  selectedNodeId.value = null
  isNodeModalOpen.value = false
}

const starterSignature = computed(() =>
  boardSignature(createStarterBoard(currentLevelId.value), customSetup.value)
)

const handleReturnClick = () => {
  const dirty = isAnonymous.value
    ? currentSignature.value !== starterSignature.value
    : hasUnsavedChanges.value
  if (!dirty) {
    void goBack('/')
    return
  }
  isQuitModalOpen.value = true
}

const confirmQuitToMenu = async () => {
  resetBoard()
  isQuitModalOpen.value = false
  await goBack('/')
}

const placeCheck = (kind: NodeKind, position: { x: number, y: number }) => {
  if (!canUseNodeKind(kind, session.value)) {
    toast.add({
      title: 'Sign in required',
      description: 'Sign in on the main menu to unlock AI agent nodes.',
      icon: 'i-lucide-lock',
      color: 'neutral'
    })
    return
  }
  const missingKey = nodeKeyRequirement(kind, nodeKeyState.value)
  if (missingKey) {
    toast.add({
      title: kind === 'jev' ? 'Jev API key missing in .env' : 'AI API key missing in .env',
      description: missingKey,
      icon: 'i-lucide-key-round',
      color: 'neutral'
    })
    return
  }
  if (isCheckDisabledByConstraints(kind, currentLevel.value.constraints)) {
    toast.add({
      title: 'Disabled in this level',
      description: `${NODE_CATALOG[kind].label} is disabled by this level's Hard constraints.`,
      icon: 'i-lucide-ban',
      color: 'neutral'
    })
    return
  }
  if (maxCheckNodes.value !== null && placedCheckNodeCount.value >= maxCheckNodes.value) {
    toast.add({
      title: 'Node limit reached',
      description: `This level allows at most ${maxCheckNodes.value} check node${maxCheckNodes.value === 1 ? '' : 's'}.`,
      icon: 'i-lucide-shield-alert',
      color: 'neutral'
    })
    return
  }
  const updated = addCheckNode({ nodes: nodes.value, edges: edges.value }, kind, position)
  syncBoard(updated)
  const newest = updated.nodes[updated.nodes.length - 1]
  if (newest) {
    selectedNodeId.value = newest.id
  }
}

const isToolLocked = (kind: NodeKind): boolean =>
  !canUseNodeKind(kind, session.value, nodeKeyState.value)
  || isCheckDisabledByConstraints(kind, currentLevel.value.constraints)

// Guided tours for the introductory levels (WEB-CAMP-007).
const levelTour = computed(() => (isCustomMode.value ? [] : levelTourSteps(currentLevelId.value)))
const hasLevelTour = computed(() => levelTour.value.length > 0)

// A step whose node is not on the board yet points at the canvas instead.
const tourTarget = (selector: string | null) => () => {
  if (!selector || !import.meta.client) return null
  return document.querySelector<HTMLElement>(selector)
    ?? document.querySelector<HTMLElement>('[data-tour="canvas"]')
}

const tour = useTour(() => levelTour.value.map(step => ({ ...step, target: tourTarget(step.target) })))
const isLastTourStep = computed(() => !tour.hasNext.value)

const startLevelTour = () => {
  isSidebarCollapsed.value = false
  isBriefingOpen.value = false
  tour.start(0)
}

const endLevelTour = () => {
  markTourSeen(currentLevelId.value)
  tour.finish()
}

const nextTourStep = () => {
  if (isLastTourStep.value) endLevelTour()
  else tour.next()
}

const handlePlaceCheck = (kind: NodeKind) => {
  const toolCount = nodes.value.filter(n => !n.data?.isAnchor).length
  placeCheck(kind, {
    x: 250 + (toolCount % 2) * 210,
    y: 90 + Math.floor(toolCount / 2) * 130
  })
}

const TOOL_DRAG_TYPE = 'application/x-shield-tool'

const onToolDragStart = (event: DragEvent, kind: NodeKind) => {
  if (!event.dataTransfer) return
  event.dataTransfer.setData(TOOL_DRAG_TYPE, kind)
  event.dataTransfer.effectAllowed = 'copy'
}

const onCanvasDragOver = (event: DragEvent) => {
  if (!event.dataTransfer?.types.includes(TOOL_DRAG_TYPE)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'copy'
}

const onCanvasDrop = (event: DragEvent) => {
  const dropped = event.dataTransfer?.getData(TOOL_DRAG_TYPE)
  const check = checks.value.find(c => c.kind === dropped)
  if (!check) return
  event.preventDefault()
  placeCheck(check.kind, screenToFlowCoordinate({ x: event.clientX, y: event.clientY }))
}

const isToolInfoOpen = ref(false)
const infoTool = ref<CheckDefinitionSchema | null>(null)

const openToolInfo = (check: CheckDefinitionSchema) => {
  infoTool.value = check
  isToolInfoOpen.value = true
}

const onNodeClick = (event: NodeMouseEvent) => {
  selectedNodeId.value = event.node.id
}

const onNodeDoubleClick = (event: NodeMouseEvent) => {
  selectedNodeId.value = event.node.id
  isNodeModalOpen.value = true
}

const onConnect = (conn: Connection) => {
  if (!conn.source || !conn.target) return
  syncBoard(
    connectBoardEdge(
      { nodes: nodes.value, edges: edges.value },
      {
        source: conn.source,
        sourceHandle: conn.sourceHandle,
        target: conn.target
      }
    )
  )
}

const updateNodeConfig = (key: string, value: unknown) => {
  if (!selectedNode.value) return
  const nextNodes = nodes.value.map((n) => {
    if (n.id !== selectedNode.value?.id || !n.data) return n
    return {
      ...n,
      data: {
        ...n.data,
        config: {
          ...n.data.config,
          [key]: value
        }
      }
    }
  })
  syncBoard({ nodes: nextNodes, edges: edges.value })
}

const customWordsList = computed<string[]>(() => {
  const raw = selectedNode.value?.data?.config.custom_words
  return Array.isArray(raw) ? raw.map(w => String(w)) : []
})

const addCustomWord = () => {
  const word = customWordDraft.value.trim()
  if (!word) return
  const next = [...customWordsList.value, word]
  updateNodeConfig('custom_words', next)
  customWordDraft.value = ''
}

const removeCustomWord = (word: string) => {
  updateNodeConfig(
    'custom_words',
    customWordsList.value.filter(w => w !== word)
  )
}

const secretPatternsList = computed<string[]>(() => {
  const raw = selectedNode.value?.data?.config.patterns
  return Array.isArray(raw) ? raw.map(p => String(p)) : []
})

const addSecretPattern = () => {
  const pattern = secretPatternDraft.value.trim()
  if (!pattern) return
  updateNodeConfig('patterns', [...secretPatternsList.value, pattern])
  secretPatternDraft.value = ''
}

const removeSecretPattern = (pattern: string) => {
  updateNodeConfig(
    'patterns',
    secretPatternsList.value.filter(p => p !== pattern)
  )
}

const textTransformsList = computed<string[]>(() => {
  const raw = selectedNode.value?.data?.config.transforms
  return Array.isArray(raw) ? raw.map(t => String(t)) : []
})

const hasTextTransform = (id: string): boolean => textTransformsList.value.includes(id)

const toggleTextTransform = (id: string) => {
  const current = textTransformsList.value
  const next = current.includes(id)
    ? current.filter(t => t !== id)
    : [...current, id]
  updateNodeConfig('transforms', next)
}

const numberedAgentTools = computed(() =>
  (levelAgent.value?.tools ?? []).map((t, index) => ({
    index: index + 1,
    name: t.name,
    allowed: t.allowed,
    label: `Tool ${index + 1}: ${formatToolName(t.name)}`
  }))
)

const blockedToolSelections = computed<Array<number | string>>(() => {
  const raw = selectedNode.value?.data?.config.block_tools
  return Array.isArray(raw)
    ? raw.filter((v): v is number | string => typeof v === 'number' || typeof v === 'string')
    : []
})

const hasBlockedToolIndex = (index: number, name: string): boolean =>
  blockedToolSelections.value.some(v => v === index || String(v) === String(index) || String(v) === name)

const toggleBlockedToolIndex = (index: number, name: string) => {
  const current = blockedToolSelections.value
  const exists = hasBlockedToolIndex(index, name)
  const next = exists
    ? current.filter(v => v !== index && String(v) !== String(index) && String(v) !== name)
    : [...current, index]
  updateNodeConfig('block_tools', next)
}

const onDatasetFileChange = async (event: Event) => {
  if (isAnonymous.value) return
  const target = event.target as { files?: FileList | null } | null
  const file = target?.files?.[0]
  if (!file) return
  const sizeCheck = checkTrainingFile(file, isCustomMode.value ? 'custom' : 'campaign')
  if (!sizeCheck.ok) {
    toast.add({
      title: 'Training error',
      description: sizeCheck.error,
      icon: 'i-lucide-triangle-alert',
      color: 'neutral'
    })
    return
  }
  const buffer = await file.arrayBuffer()
  const decoded = decodeTrainingCsv(buffer)
  if (!decoded.ok) {
    toast.add({
      title: 'Training error',
      description: decoded.error,
      icon: 'i-lucide-triangle-alert',
      color: 'neutral'
    })
    return
  }
  mlCsvDraft.value = decoded.text
  await handleTrainCustomMl()
}

const handleTrainCustomMl = async (confirmedReplace = false) => {
  if (isAnonymous.value) return
  if (!selectedNode.value || selectedNode.value.data?.kind !== 'ml_classifier') return
  if (
    !confirmedReplace
    && needsReplaceConfirmation(nodes.value, selectedNode.value.id, activeSessionModelId.value)
  ) {
    isReplaceModelConfirmOpen.value = true
    return
  }
  isReplaceModelConfirmOpen.value = false
  const targetId = selectedNode.value.id
  const algo = String(selectedNode.value.data.config.algorithm || 'tfidf')
  mlTraining.value = true
  try {
    const res = await trainClassifier({
      algorithm: algo,
      csv_text: mlCsvDraft.value,
      level_id: isCustomMode.value ? 'custom' : currentLevelId.value
    })
    activeSessionModelId.value = res.model_id
    syncBoard({
      nodes: applyTrainedModelToBoard(nodes.value, targetId, res.model_id),
      edges: edges.value
    })
    mlTrainStats.value = {
      sampleCount: res.sample_count,
      accuracy: res.accuracy
    }
    await refreshSession()
    toast.add({
      title: 'Model trained',
      description: `${res.sample_count} samples (${(res.accuracy * 100).toFixed(0)}% accuracy)`,
      icon: 'i-lucide-check',
      color: 'neutral'
    })
  } catch (err) {
    const msg = (err as { data?: { detail?: string } }).data?.detail ?? 'Check CSV format (text,label).'
    toast.add({
      title: 'Training error',
      description: msg,
      icon: 'i-lucide-triangle-alert',
      color: 'neutral'
    })
  } finally {
    mlTraining.value = false
  }
}

const selectedCheck = computed(() =>
  checks.value.find(c => c.kind === selectedNode.value?.data?.kind) ?? null
)

// The final node's job, shown under its modal title on every level (WEB-LEVEL-005).
const FINAL_NODE_HINT = 'Wire your last check here. Everything that arrives gets answered, so only let safe prompts through.'

const nodeModalDescription = computed(() => {
  const data = selectedNode.value?.data
  if (!data) return ''
  if (data.kind === 'assistant') return FINAL_NODE_HINT
  return nodeCostLine(
    selectedCheck.value?.latency_ms ?? data.latencyMs,
    selectedCheck.value?.cost_usd ?? data.costUsd
  )
})

// Run results (WEB-AGENT-011): where every prompt of the last wave ended up.
const isResultsOpen = ref(false)
const resultsMatrix = computed(() => confusionMatrix(traces.value))
type ResultCellKey = 'normalPassed' | 'normalStopped' | 'attackPassed' | 'attackStopped'

// Matrix cells in reading order: rows Normal then Injection, columns Got through then Stopped.
const resultCells = computed(() => [
  { key: 'normalPassed' as const, rowLabel: 'Normal', caption: 'True Positive', title: 'Normal prompts that got through', correct: true, items: resultsMatrix.value.normalPassed },
  { key: 'normalStopped' as const, rowLabel: '', caption: 'False Negative', title: 'Normal prompts that were stopped', correct: false, items: resultsMatrix.value.normalStopped },
  { key: 'attackPassed' as const, rowLabel: 'Injection', caption: 'False Positive', title: 'Injections that got through', correct: false, items: resultsMatrix.value.attackPassed },
  { key: 'attackStopped' as const, rowLabel: '', caption: 'True Negative', title: 'Injections stopped', correct: true, items: resultsMatrix.value.attackStopped }
])

const isBreakdownOpen = ref(false)
// One collapsible item for the per-component points (WEB-AGENT-021); collapsed by default.
const breakdownAccordionItems = [{ label: 'Score breakdown', value: 'points' }]
const isResultCellOpen = ref(false)
const selectedResultCellKey = ref<ResultCellKey>('attackPassed')
const selectedResultCell = computed(() =>
  resultCells.value.find(cell => cell.key === selectedResultCellKey.value) ?? resultCells.value[0]!
)
const openResultCell = (key: ResultCellKey) => {
  selectedResultCellKey.value = key
  isResultCellOpen.value = true
}

const agentRules = computed<string[]>(() =>
  selectedNode.value?.data ? agentRulesFrom(selectedNode.value.data.config) : []
)
const ruleDraft = ref('')

const addRuleFromDraft = () => {
  if (!canAddAgentRule(agentRules.value) || !ruleDraft.value.trim()) return
  updateNodeConfig('rules', addAgentRule(agentRules.value, ruleDraft.value))
  ruleDraft.value = ''
}

const updateAgentRule = (index: number, text: string) => {
  updateNodeConfig(
    'rules',
    agentRules.value.map((rule, i) => (i === index ? text.slice(0, AGENT_RULE_MAX_CHARS) : rule))
  )
}

const removeAgentRule = (index: number) => {
  updateNodeConfig('rules', agentRules.value.filter((_, i) => i !== index))
}

// Anonymous players are asked to sign in to save (spec 0023); runs start straight away (WEB-AGENT-015).
const isSignInPromptOpen = ref(false)

const openSignInPrompt = (_kind: 'save') => {
  isSignInPromptOpen.value = true
}

// Easy and Custom cost no runs, so the attempts counter shows only where the quota applies.
const showAttempts = computed(() => !isCustomMode.value && levelAgent.value !== null && attemptsLeftLabel(session.value) !== '')

// Saved boards (spec 0023): one save per player and level, never holding the API key.
const saveLevelKey = computed(() => isCustomMode.value ? 'custom' as const : currentLevelId.value)
const saveOwnerKey = computed(() => session.value.email || session.value.player_name || 'player')
const savingBoard = ref(false)
const isLoadingBoard = ref(false)
const savedSignature = ref('')
const customSetup = computed(() => isCustomMode.value
  ? {
      agent: apiCustomAgent.value,
      dataset: customDataset.value.rows,
      provider: customProvider.value,
      model: customModel.value
    }
  : null)
const currentSignature = computed(() =>
  boardSignature({ nodes: nodes.value, edges: edges.value }, customSetup.value)
)
const hasUnsavedChanges = computed(() => !isAnonymous.value && currentSignature.value !== savedSignature.value)
const markSaved = () => {
  savedSignature.value = currentSignature.value
}

const applySavePayload = (save: Parameters<typeof boardFromSave>[0]) => {
  const restored = boardFromSave(save, currentLevelId.value)
  if (!restored) {
    resetBoard()
    toast.add({
      title: 'Your saved board could not be loaded',
      description: 'It uses nodes that no longer exist, so the starter board is shown.',
      icon: 'i-lucide-triangle-alert',
      color: 'neutral'
    })
  } else {
    syncBoard({
      nodes: markUntrainedModelNodes(restored.nodes, [], { allMl: true }),
      edges: restored.edges
    })
    if (isCustomMode.value && save.custom) {
      // The key is never saved, so it stays whatever the player typed this visit.
      customAgent.value = { objective: save.custom.agent.objective, tools: [...(save.custom.agent.tools ?? [])] }
      customDatasetText.value = datasetRowsToCsv(
        (save.custom.dataset ?? []).map(r => ({ ...r, expected_tool: r.expected_tool ?? null }))
      )
      customProvider.value = save.custom.provider ?? 'openai'
      customModel.value = save.custom.model ?? ''
    }
  }
}

const persistBoard = async () => {
  const payload = saveFromBoard({ nodes: nodes.value, edges: edges.value }, customSetup.value)
  await putSave(saveLevelKey.value, payload)
  setCachedBoard(saveOwnerKey.value, saveLevelKey.value, payload)
  markSaved()
}

const handleSaveBoard = async () => {
  savingBoard.value = true
  try {
    await persistBoard()
    toast.add({ title: 'Saved', icon: 'i-lucide-check', color: 'neutral' })
  } catch (err) {
    const detail = (err as { data?: { detail?: string } }).data?.detail ?? 'Try again in a moment.'
    toast.add({ title: 'Save failed', description: detail, icon: 'i-lucide-triangle-alert', color: 'neutral' })
  } finally {
    savingBoard.value = false
  }
}

// Seed the header's High Score with the stored best (WEB-AGENT-019).
const loadStoredHighScore = async () => {
  if (isAnonymous.value || isCustomMode.value) return
  const levelId = currentLevelId.value
  try {
    const stored = levelHighScore(await getProgress(), levelId)
    if (levelId !== currentLevelId.value || stored.score === null) return
    if (highScore.value === null || stored.score > highScore.value) {
      highScore.value = stored.score
      highStars.value = stored.stars
    }
  } catch (err) {
    console.warn('Stored progress unavailable:', err)
  }
}

const loadSavedBoard = async () => {
  if (isAnonymous.value) {
    markSaved()
    isLoadingBoard.value = false
    return
  }
  const cached = getCachedBoard(saveOwnerKey.value, saveLevelKey.value)
  if (cached) {
    applySavePayload(cached)
    markSaved()
    isLoadingBoard.value = false
  } else {
    isLoadingBoard.value = true
  }
  try {
    const save = await getSave(saveLevelKey.value)
    setCachedBoard(saveOwnerKey.value, saveLevelKey.value, save)
    if (!cached || JSON.stringify(save.board) !== JSON.stringify(cached.board) || JSON.stringify(save.positions) !== JSON.stringify(cached.positions)) {
      applySavePayload(save)
    }
  } catch (err) {
    if ((err as { statusCode?: number }).statusCode !== 404) {
      console.warn('Saved board unavailable:', err)
    }
  } finally {
    isLoadingBoard.value = false
  }
  markSaved()
}

const handleRunWave = async (singleMessage?: string) => {
  runningWave.value = true
  syncBoard(markBoardRunning(resetBoardStatuses({ nodes: nodes.value, edges: edges.value })))
  try {
    const response = await runWithAnonymousRetry(
      () => runGame({
        level_id: isCustomMode.value ? 'custom' : currentLevelId.value,
        board: toApiBoard({ nodes: nodes.value, edges: edges.value }),
        custom_message: singleMessage ?? null,
        custom: isCustomMode.value
          ? {
              agent: apiCustomAgent.value,
              dataset: customDataset.value.rows,
              model: { provider: customProvider.value, model: customModel.value, api_key: customApiKey.value }
            }
          : null
      }),
      continueAnonymously
    )
    traces.value = response.traces
    waveScore.value = response.score
    if (!singleMessage) {
      newRecord.value = isNewRecord(highScore.value, response.score.total_score)
      highStars.value = nextHighStars(highScore.value, highStars.value, response.score.total_score, waveStars(response.score))
      highScore.value = nextHighScore(highScore.value, response.score.total_score)
    }
    if (!singleMessage) isResultsOpen.value = true
    const summarized = applyWaveSummary(
      { nodes: nodes.value, edges: edges.value },
      response.traces
    )
    const untrainedList = response.untrained_model_nodes ?? []
    syncBoard({
      nodes: untrainedList.length > 0
        ? markUntrainedModelNodes(summarized.nodes, untrainedList)
        : summarized.nodes,
      edges: summarized.edges
    })
    if (activeSessionModelId.value && untrainedList.length > 0) {
      const stillTrained = nodes.value.some(
        n => n.data?.kind === 'ml_classifier' && n.data?.config.model_id === activeSessionModelId.value
      )
      if (!stillTrained) {
        activeSessionModelId.value = null
      }
    }
    if (!singleMessage && response.score.won && !isAnonymous.value) {
      void persistBoard().catch(err => console.warn('Auto-save failed:', err))
    }
    await refreshSession()
    if (!singleMessage && !isAnonymous.value && response.agent_mode === 'live') {
      void refreshScores({ background: true })
      toast.add({
        title: 'Score recorded',
        description: `${response.score.total_score.toLocaleString()} points recorded on the leaderboard.`,
        icon: 'i-lucide-trophy',
        color: 'neutral'
      })
    }
  } catch (err) {
    syncBoard(resetBoardStatuses({ nodes: nodes.value, edges: edges.value }))
    const detail = errorDetail(err, 'Place at least one tool node between Input and the final node.')
    toast.add({
      title: 'Run blocked',
      description: detail,
      icon: 'i-lucide-triangle-alert',
      color: 'neutral'
    })
  } finally {
    runningWave.value = false
  }
}

const handleTestCustomMessage = async () => {
  const text = customMessage.value.trim()
  if (!text) return
  await handleRunWave(text)
}

watch(
  () => route.query.level,
  (val) => {
    if (isValidLevelId(val)) {
      currentLevelId.value = val
      highScore.value = null
      highStars.value = 0
      resetBoard()
      void loadSavedBoard()
      void loadStoredHighScore()
    }
  }
)

onMounted(async () => {
  const cached = !isAnonymous.value ? getCachedBoard(saveOwnerKey.value, saveLevelKey.value) : null
  if (cached) {
    applySavePayload(cached)
    markSaved()
  } else if (!isAnonymous.value) {
    isLoadingBoard.value = true
  }

  const sessionTask = refreshSession().then(async () => {
    if (!session.value.authenticated) {
      await continueAnonymously()
    }
    if (isCustomMode.value && customModeAccess(session.value) !== 'available') {
      await navigateTo('/')
      return false
    }
    return true
  })

  const catalogTask = getLevels()
    .then((catalog) => {
      if (catalog.levels.length > 0) levels.value = catalog.levels
      if (catalog.checks.length > 0) checks.value = catalog.checks
      jevKeyConfigured.value = Boolean(catalog.jev_key_configured)
      aiKeyConfigured.value = Boolean(catalog.ai_key_configured)
    })
    .catch((err) => {
      console.warn('Using built-in level defaults:', err)
    })

  // Start save fetch concurrently when already signed in; otherwise load right after sessionTask.
  const saveTask = !isAnonymous.value
    ? loadSavedBoard()
    : sessionTask.then(ok => (ok ? loadSavedBoard() : undefined))

  const highScoreTask = sessionTask.then(ok => (ok ? loadStoredHighScore() : undefined))
  await Promise.all([sessionTask, catalogTask, saveTask, highScoreTask])
  isLoadingBoard.value = false

  if (hasLevelTour.value && !isProLevelLocked.value && !hasSeenTour(currentLevelId.value)) {
    await nextTick()
    startLevelTour()
  }
})

if (import.meta.client) {
  const onPageHide = () => {
    triggerBeaconPurge(navigator)
  }
  onMounted(() => {
    window.addEventListener('pagehide', onPageHide)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('pagehide', onPageHide)
  })
}

onBeforeRouteLeave(() => {
  void purgeModels().catch(() => {})
})
</script>

<template>
  <div class="flex h-dvh w-screen flex-col overflow-hidden bg-default text-default">
    <!-- Top Nav 1: Return button + Level Name (left) | Quota + Current Score (right) -->
    <header class="flex h-14 shrink-0 items-center justify-between border-b border-default px-4">
      <div class="flex items-center gap-3 min-w-0">
        <UButton
          label="Return"
          icon="i-lucide-arrow-left"
          color="neutral"
          variant="ghost"
          size="lg"
          @click="handleReturnClick"
        />

        <h1 class="text-base text-md font-bold text-highlighted truncate">
          {{ currentLevel.title }}
        </h1>

        <UButton
          v-if="!isCustomMode"
          icon="i-lucide-circle-question-mark"
          color="neutral"
          variant="ghost"
          size="sm"
          @click="isBriefingOpen = true"
        />
      </div>

      <div class="flex items-center gap-3">
        <UButton
          v-if="isLoggedIn && !isPaid"
          label="Upgrade"
          icon="i-lucide-sparkles"
          color="neutral"
          variant="outline"
          size="md"
          to="/plans"
        />

        <div class="flex items-center gap-3 pl-2">
          <template v-if="waveScore">
            <UButton
              label="Results"
              icon="i-lucide-grid-2x2"
              color="neutral"
              variant="outline"
              size="md"
              @click="isResultsOpen = true"
            />
            <USeparator
              orientation="vertical"
              class="h-5"
            />
          </template>
          <span class="text-md">
            High Score: {{ (highScore ?? 0).toLocaleString() }}
          </span>
          <UInputRating
            :model-value="highStars"
            :length="3"
            readonly
            color="warning"
            :aria-label="`${highStars} of 3 stars`"
          />
        </div>
      </div>
    </header>

    <!-- Top Nav 2: Replaces bottom nav (Wave controls + Custom test bar) -->
    <div class="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-default bg-elevated/30 px-4">
      <div class="flex items-center gap-2">
        <UButton
          label="Run wave"
          data-tour="run-wave"
          icon="i-lucide-play"
          color="neutral"
          variant="solid"
          size="lg"
          :loading="runningWave"
          :disabled="isCustomMode && !canRunCustom(customAgent, customDataset, customApiKey) || (showAttempts && runsRemaining(session, 'wave') === 0)"
          @click="handleRunWave()"
        />

        <UButton
          label="Restart"
          icon="i-lucide-rotate-ccw"
          color="neutral"
          variant="ghost"
          size="lg"
          @click="resetBoard"
        />

        <UChip
          :show="hasUnsavedChanges"
          color="primary"
          size="md"
        >
          <UButton
            label="Save"
            icon="i-lucide-save"
            color="neutral"
            variant="ghost"
            size="lg"
            :loading="savingBoard"
            :aria-label="hasUnsavedChanges ? 'Save (unsaved changes)' : 'Save'"
            @click="isAnonymous ? openSignInPrompt('save') : handleSaveBoard()"
          />
        </UChip>

        <UButton
          v-if="hasLevelTour"
          label="Guide"
          icon="i-lucide-map"
          color="neutral"
          variant="ghost"
          size="lg"
          @click="startLevelTour"
        />

        <template v-if="showAttempts">
          <USeparator
            orientation="vertical"
            class="h-5 px-1"
          />
          <span class="text-sm tabular-nums text-muted">
            {{ attemptsLeftLabel(session) }}
          </span>
        </template>

        <template v-if="maxCheckNodes !== null">
          <USeparator
            orientation="vertical"
            class="h-5 px-1"
          />
          <UBadge
            :label="`${placedCheckNodeCount} / ${maxCheckNodes} nodes`"
            :color="placedCheckNodeCount > maxCheckNodes ? 'warning' : 'neutral'"
            variant="subtle"
            size="sm"
          />
        </template>
      </div>

      <div
        class="flex items-center gap-2 w-full max-w-md"
        data-tour="test-bar"
      >
        <UInput
          v-model="customMessage"
          placeholder="Test a message..."
          size="lg"
          class="flex-1"
          @keydown.enter="handleTestCustomMessage()"
        />
        <UButton
          label="Test"
          icon="i-lucide-send"
          color="neutral"
          variant="solid"
          size="lg"
          :loading="runningWave"
          @click="handleTestCustomMessage()"
        />
      </div>
    </div>

    <!-- Main Workspace: Collapsible Left Tools Panel + Full Canvas -->
    <div class="relative flex flex-1 min-h-0 overflow-hidden">
      <!-- Left Panel: Tools -->
      <div
        class="relative z-10 flex shrink-0 h-full"
        :class="isSidebarCollapsed ? 'w-0' : 'w-88'"
      >
        <aside
          v-show="!isSidebarCollapsed"
          class="flex h-full w-full cursor-default flex-col border-r border-default bg-elevated/20 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          <div class="border-b border-default px-3 py-3">
            <h2 class="text-sm font-bold uppercase tracking-wider text-highlighted">
              Tools
            </h2>
          </div>

          <div class="grid grid-cols-2 gap-2 p-2.5">
            <UCard
              v-for="chk in checks"
              :key="chk.kind"
              role="button"
              tabindex="0"
              :aria-label="`Add ${chk.label}`"
              :data-tour="`tool-${chk.kind}`"
              :aria-disabled="isToolLocked(chk.kind)"
              :ui="toolCardUi"
              :class="isToolLocked(chk.kind) ? 'cursor-not-allowed opacity-50 hover:opacity-100 focus-visible:opacity-100' : 'cursor-pointer'"
              :draggable="!isToolLocked(chk.kind)"
              @click="handlePlaceCheck(chk.kind)"
              @keydown.enter.self="handlePlaceCheck(chk.kind)"
              @keydown.space.self.prevent="handlePlaceCheck(chk.kind)"
              @dragstart="onToolDragStart($event, chk.kind)"
            >
              <template #header>
                <div class="flex items-center justify-between gap-1">
                  <span class="min-w-0 truncate text-xs font-bold text-highlighted">
                    {{ chk.label }}
                  </span>
                  <UButton
                    icon="i-lucide-info"
                    color="neutral"
                    variant="ghost"
                    size="xs"
                    square
                    :aria-label="`About ${chk.label}`"
                    class="relative z-20 -my-1 shrink-0"
                    @click.stop="openToolInfo(chk)"
                  />
                </div>
              </template>

              <div class="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-default/60 p-3 text-center text-xs font-medium text-highlighted opacity-0 backdrop-blur-sm transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                {{ isCheckDisabledByConstraints(chk.kind, currentLevel.constraints) ? 'Disabled in this level' : !canUseNodeKind(chk.kind, session) ? 'Sign in to unlock' : (nodeKeyRequirement(chk.kind, nodeKeyState) || 'Click or drag into canvas') }}
              </div>

              <UIcon
                :name="NODE_CATALOG[chk.kind]?.icon || 'i-lucide-box'"
                class="size-7 shrink-0 text-muted"
              />
              <p class="line-clamp-2 text-xs leading-tight text-muted">
                {{ NODE_CATALOG[chk.kind]?.subtitle }}
              </p>

              <template #footer>
                <div
                  v-if="!isToolLocked(chk.kind)"
                  class="flex items-center justify-between gap-1 text-xs tabular-nums text-dimmed"
                >
                  <span>{{ chk.latency_ms.toFixed(0) }}ms</span>
                  <span>{{ formatCheckCost(chk.cost_usd) }}</span>
                </div>
                <div
                  v-else-if="isCheckDisabledByConstraints(chk.kind, currentLevel.constraints)"
                  class="flex items-center justify-center gap-1 text-xs text-dimmed"
                >
                  <UIcon
                    name="i-lucide-ban"
                    class="size-3 shrink-0"
                  />
                  <span>Disabled</span>
                </div>
                <div
                  v-else
                  class="flex items-center justify-center gap-1 text-xs text-dimmed"
                >
                  <UIcon
                    name="i-lucide-lock"
                    class="size-3 shrink-0"
                  />
                  <span>{{ !canUseNodeKind(chk.kind, session) ? 'Sign in' : 'API key' }}</span>
                </div>
              </template>
            </UCard>
          </div>
        </aside>

        <!-- Middle-right collapsible close / expand button -->
        <UButton
          :icon="isSidebarCollapsed ? 'i-lucide-chevron-right' : 'i-lucide-chevron-left'"
          color="neutral"
          variant="outline"
          size="lg"
          square
          :aria-label="isSidebarCollapsed ? 'Open tools sidebar' : 'Close tools sidebar'"
          :class="[
            'absolute top-1/2 z-40 -translate-y-1/2 bg-default',
            isSidebarCollapsed ? 'left-2' : 'right-0 translate-x-1/2'
          ]"
          @click="isSidebarCollapsed = !isSidebarCollapsed"
        />
      </div>

      <!-- Center Canvas -->
      <main
        class="relative isolate flex-1 h-full min-w-0 bg-default"
        data-tour="canvas"
        @dragover="onCanvasDragOver"
        @drop="onCanvasDrop"
      >
        <VueFlow
          :id="FLOW_ID"
          v-model:nodes="nodes"
          v-model:edges="edges"
          :default-zoom="0.95"
          :min-zoom="0.35"
          :max-zoom="1.75"
          fit-view-on-init
          class="h-full w-full"
          @nodes-change="onNodesChange"
          @edges-change="onEdgesChange"
          @node-click="onNodeClick"
          @node-double-click="onNodeDoubleClick"
          @connect="onConnect"
        >
          <template #node-gameNode="nodeProps">
            <GameNode v-bind="nodeProps" />
          </template>

          <Background
            :gap="20"
            :size="1"
            color="var(--ui-border-accented)"
          />
        </VueFlow>

        <div
          v-if="isProLevelLocked"
          class="absolute inset-0 z-30 flex items-center justify-center bg-default/85 p-6 backdrop-blur-sm"
        >
          <UCard
            variant="outline"
            :ui="{ root: 'w-full max-w-md', body: 'space-y-4 p-6 text-center' }"
          >
            <div class="mx-auto flex size-12 items-center justify-center rounded-full border border-default bg-elevated text-highlighted">
              <UIcon
                name="i-lucide-lock"
                class="size-5"
              />
            </div>
            <div class="space-y-1">
              <h2 class="text-lg font-bold text-highlighted">
                Pro Level Locked
              </h2>
              <p class="text-sm text-muted">
                {{ currentLevel.title }} is part of the Pro campaign. Upgrade your plan to play all 23 campaign levels.
              </p>
            </div>
            <div class="flex flex-wrap items-center justify-center gap-2 pt-2">
              <UButton
                to="/plans"
                label="Upgrade to Pro"
                icon="i-lucide-sparkles"
                color="neutral"
                variant="solid"
                size="md"
              />
            </div>
          </UCard>
        </div>

        <div
          v-else-if="isLoadingBoard"
          class="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 bg-default/80 backdrop-blur-sm"
        >
          <UIcon
            name="i-lucide-loader-circle"
            class="size-6 animate-spin text-highlighted"
          />
          <p class="text-sm font-medium text-muted">
            Loading workflow...
          </p>
        </div>
      </main>
    </div>

    <!-- Tool Info Modal -->
    <UModal
      v-model:open="isToolInfoOpen"
      :title="infoTool?.label ?? 'Tool details'"
    >
      <template #body>
        <div
          v-if="infoTool"
          class="space-y-4 text-sm"
        >
          <p class="text-default">
            {{ infoTool.summary }}
          </p>
          <dl class="space-y-3 border-t border-default pt-4">
            <div class="flex items-center justify-between gap-4">
              <dt class="text-muted">
                Latency
              </dt>
              <dd class="font-medium tabular-nums text-highlighted">
                {{ infoTool.latency_ms }} ms
              </dd>
            </div>
            <div class="flex items-center justify-between gap-4">
              <dt class="text-muted">
                Cost per message
              </dt>
              <dd class="font-medium tabular-nums text-highlighted">
                {{ formatCheckCost(infoTool.cost_usd) }}
              </dd>
            </div>
          </dl>
        </div>
      </template>
    </UModal>

    <!-- Sign-in prompt shown to anonymous players who try to save -->
    <UModal
      v-model:open="isSignInPromptOpen"
      title="Sign in to save your board"
    >
      <template #body>
        <p class="text-sm text-default">
          Sign in to save your board. Saved boards come back when you open the level again, on any device.
        </p>
      </template>

      <template #footer>
        <div class="flex w-full items-center justify-end gap-2">
          <UButton
            to="/auth/login"
            label="Sign in"
            color="neutral"
            variant="solid"
            size="md"
          />
        </div>
      </template>
    </UModal>

    <!-- Quit Confirmation Modal -->
    <UModal
      v-model:open="isQuitModalOpen"
      title="Quit Game"
    >
      <template #body>
        <p class="text-base text-default">
          Are you sure you want to quit? Your progress will not be saved
        </p>
      </template>

      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            label="Cancel"
            color="neutral"
            variant="ghost"
            size="md"
            @click="isQuitModalOpen = false"
          />
          <UButton
            label="Quit"
            color="error"
            variant="solid"
            size="md"
            @click="confirmQuitToMenu"
          />
        </div>
      </template>
    </UModal>

    <!-- Run Results Modal: stars and score of the last wave (WEB-AGENT-020) -->
    <UModal
      v-model:open="isResultsOpen"
      title="Run results"
      :ui="{ content: 'sm:max-w-2xl' }"
    >
      <template #body>
        <div class="space-y-8">
          <div
            v-if="waveScore"
            class="flex flex-col items-center gap-3 text-center"
          >
            <UInputRating
              :model-value="waveStars(waveScore)"
              :length="3"
              readonly
              color="warning"
              size="xl"
              :aria-label="`${waveStars(waveScore)} of 3 stars`"
            />
            <div class="space-y-1">
              <p class="text-4xl font-bold tabular-nums text-highlighted">
                {{ waveScore.total_score.toLocaleString() }}
              </p>
              <div class="flex flex-col items-center justify-center gap-2">
                <div v-if="waveScore.won">
                  <p class="font-bold text-xl py-1">
                    Victory
                  </p>
                </div>
                <div v-if="waveScore.won === false">
                  <p class="font-bold text-xl py-1">
                    Defeat
                  </p>
                </div>
                <UBadge
                  v-if="newRecord"
                  label="New record!"
                  icon="i-lucide-trophy"
                  color="warning"
                  variant="subtle"
                />
              </div>
              <p
                v-if="!waveScore.won"
                class="text-xs text-muted"
              >
                {{ waveOutcomeSummary(waveScore) }}
              </p>
            </div>

            <div
              v-if="waveScore.constraint_violations && waveScore.constraint_violations.length > 0"
              class="w-full max-w-md space-y-2 text-left"
            >
              <UAlert
                v-for="violation in waveScore.constraint_violations"
                :key="violation"
                icon="i-lucide-shield-alert"
                title="Hard constraint violated"
                color="neutral"
                variant="subtle"
              >
                <template #description>
                  {{ violation }}
                </template>
              </UAlert>
            </div>

            <UButton
              label="Show breakdown"
              icon="i-lucide-list"
              color="neutral"
              variant="outline"
              size="sm"
              @click="isBreakdownOpen = true"
            />
          </div>

          <UEmpty
            v-else
            icon="i-lucide-play"
            title="No runs yet"
            description="Run a wave to see which prompts got through and which were stopped."
            size="sm"
            variant="naked"
          />
        </div>
      </template>

      <template #footer>
        <div class="flex w-full flex-wrap items-center justify-between gap-2">
          <div class="ml-auto flex items-center gap-2">
            <UButton
              v-if="waveScore?.won && nextLevel"
              :to="canAccessLevel(nextLevel, session) === 'available' ? `/game?level=${nextLevel.id}` : '/plans'"
              label="Next Level"
              trailing-icon="i-lucide-arrow-right"
              color="neutral"
              variant="outline"
              size="md"
              @click="isResultsOpen = false"
            />
            <UButton
              label="Done"
              color="neutral"
              variant="solid"
              size="md"
              @click="isResultsOpen = false"
            />
          </div>
        </div>
      </template>
    </UModal>

    <!-- Mission Briefing Modal -->
    <CampaignLevelBriefingModal
      v-model:open="isBriefingOpen"
      :level="currentLevel"
      :stage-number="String(currentLevel.order).padStart(2, '0')"
      :stars="highStars"
      :best-score="highScore ?? 0"
      :won="Boolean(waveScore?.won)"
      :mastered="Boolean(waveScore?.follow_up_passed)"
      in-game
    />

    <!-- Score Breakdown Modal, opened from Run results (WEB-AGENT-021) -->
    <UModal
      v-model:open="isBreakdownOpen"
      title="Score breakdown"
      :ui="{ content: 'sm:max-w-2xl' }"
    >
      <template #body>
        <div
          v-if="waveScore"
          class="space-y-6"
        >
          <div class="grid grid-cols-3 divide-x divide-default rounded-lg border border-default bg-elevated/30">
            <div
              v-for="stat in [
                { icon: 'i-lucide-timer', label: 'Avg latency', value: `${waveScore.avg_latency_ms.toFixed(1)} ms` },
                { icon: 'i-lucide-coins', label: 'Cost', value: `$${waveScore.total_cost_usd.toFixed(4)}` },
                { icon: 'i-lucide-cpu', label: 'Agent tokens', value: waveScore.total_tokens.toLocaleString() }
              ]"
              :key="stat.label"
              class="min-w-0 px-4 py-3"
            >
              <p class="flex items-center gap-1.5 text-xs text-muted">
                <UIcon
                  :name="stat.icon"
                  class="size-3.5 shrink-0"
                />
                <span class="truncate">{{ stat.label }}</span>
              </p>
              <p class="mt-1 truncate text-lg font-semibold tabular-nums text-highlighted">
                {{ stat.value }}
              </p>
            </div>
          </div>

          <UAccordion
            :items="breakdownAccordionItems"
          >
            <template #body>
              <dl class="divide-y divide-default text-sm">
                <div
                  v-for="row in scoreBreakdown(waveScore, currentLevelId)"
                  :key="row.label"
                  class="flex items-center justify-between py-2 tabular-nums"
                >
                  <dt class="text-muted">
                    {{ row.label }}
                  </dt>
                  <dd :class="['font-medium', row.points < 0 ? 'text-error' : row.points > 0 ? 'text-highlighted' : 'text-dimmed']">
                    {{ (row.points || 0).toLocaleString() }}
                  </dd>
                </div>
                <div class="flex items-center justify-between pt-3 tabular-nums">
                  <dt class="font-semibold text-highlighted">
                    Total
                  </dt>
                  <dd class="text-base font-bold text-highlighted">
                    {{ waveScore.total_score.toLocaleString() }}
                  </dd>
                </div>
              </dl>
            </template>
          </UAccordion>

          <div
            v-if="traces.length > 0"
            class="space-y-3"
          >
            <div class="flex items-center gap-1">
              <h3 class="text-sm font-semibold text-highlighted">
                Prompt outcomes
              </h3>
              <UTooltip text="Click a cell to see the prompts">
                <UButton
                  icon="i-lucide-circle-question-mark"
                  size="sm"
                  variant="link"
                />
              </UTooltip>
            </div>
            <div class="grid grid-cols-[auto_1fr_1fr] gap-x-3 gap-y-2">
              <span />
              <span class="text-center text-xs font-medium text-muted">Got through</span>
              <span class="text-center text-xs font-medium text-muted">Stopped</span>

              <template
                v-for="cell in resultCells"
                :key="cell.key"
              >
                <span
                  v-if="cell.rowLabel"
                  class="self-center pe-1 text-right text-xs font-medium text-muted"
                >
                  {{ cell.rowLabel }}
                </span>
                <UButton
                  color="neutral"
                  variant="ghost"
                  :class="[
                    'group w-full flex-col items-center gap-1 rounded-xl py-5',
                    cell.items.length === 0
                      ? 'bg-elevated/30 hover:bg-elevated/60'
                      : cell.correct
                        ? 'bg-success/10 hover:bg-success/15'
                        : 'bg-error/10 hover:bg-error/15'
                  ]"
                  :aria-label="`${cell.title}: ${cell.items.length}. Show prompts`"
                  @click="openResultCell(cell.key)"
                >
                  <span :class="['text-3xl font-semibold tabular-nums', cell.items.length === 0 ? 'text-dimmed' : cell.correct ? 'text-success' : 'text-error']">
                    {{ cell.items.length }}
                  </span>
                  <span class="flex items-center gap-1.5 text-xs font-normal text-muted">
                    {{ cell.caption }}
                  </span>
                </UButton>
              </template>
            </div>
          </div>
        </div>
      </template>
    </UModal>

    <!-- Matrix Cell Modal: the prompts in one confusion-matrix cell -->
    <UModal
      v-model:open="isResultCellOpen"
      :title="selectedResultCell.title"
      :ui="{
        content: 'sm:max-w-2xl',
        body: '[scrollbar-gutter:stable] [scrollbar-width:thin] [scrollbar-color:var(--ui-border-accented)_transparent]'
      }"
    >
      <template #body>
        <ul
          v-if="selectedResultCell.items.length > 0"
          class="divide-y divide-default rounded-md border border-default"
        >
          <li
            v-for="item in selectedResultCell.items"
            :key="item.message_id"
            class="px-4 py-3 text-sm text-default"
          >
            {{ item.text }}
          </li>
        </ul>
      </template>
    </UModal>

    <!-- Double-Click Node Settings Modal -->
    <UModal
      v-model:open="isNodeModalOpen"
      :title="selectedNode?.data?.label || ''"
      :description="nodeModalDescription"
      :ui="{
        content: 'sm:max-w-2xl',
        body: '[scrollbar-gutter:stable] [scrollbar-width:thin] [scrollbar-color:var(--ui-border-accented)_transparent]'
      }"
    >
      <template #body>
        <div
          v-if="selectedNode && selectedNode.data"
          class="space-y-7"
        >
          <!-- Input: what the node does -->
          <section
            v-if="selectedNode.data.kind === 'incoming'"
            class="space-y-2"
          >
            <h3 class="text-sm font-semibold text-highlighted">
              What this node does
            </h3>
            <blockquote class="rounded-md border border-default bg-elevated/50 px-4 py-3 text-sm leading-relaxed text-default">
              Connect the node with a tool and the prompt will flow into the next node.
            </blockquote>
          </section>

          <!-- Help Desk (Easy): no model runs, so there is nothing to configure -->
          <section
            v-else-if="selectedNode.data.kind === 'assistant' && !levelAgent"
            class="space-y-2"
          >
            <h3 class="text-sm font-semibold text-highlighted">
              What this node does
            </h3>
            <blockquote class="rounded-md border border-default bg-elevated/50 px-4 py-3 text-sm leading-relaxed text-default">
              Every prompt that reaches the help desk is answered. Stop the injections before they get here.
            </blockquote>
          </section>

          <!-- Protected Agent: system instruction, tools and rules -->
          <template v-else-if="selectedNode.data.kind === 'assistant' && levelAgent">
            <div class="space-y-7">
              <!-- Custom sandbox: the player's own model, objective, tools and dataset -->
              <template v-if="isCustomMode">
                <section class="space-y-2">
                  <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                    Model
                    <UTooltip text="Runs on your own key. The key stays in this tab and is sent only with each run.">
                      <UIcon
                        name="i-lucide-circle-question-mark"
                        class="size-3.5 text-dimmed"
                      />
                    </UTooltip>
                  </h3>
                  <div class="grid gap-3 sm:grid-cols-2">
                    <UFormField label="Provider">
                      <USelect
                        v-model="customProvider"
                        :items="providerItems"
                        class="w-full"
                      />
                    </UFormField>
                    <UFormField label="Model">
                      <UInput
                        v-model="customModel"
                        :maxlength="CUSTOM_LIMITS.modelChars"
                        placeholder="gpt-4.1-mini"
                        class="w-full"
                      />
                    </UFormField>
                  </div>
                  <UFormField label="API key">
                    <UInput
                      v-model="customApiKey"
                      type="password"
                      autocomplete="off"
                      :maxlength="CUSTOM_LIMITS.keyChars"
                      placeholder="Paste your key"
                      class="w-full"
                    />
                  </UFormField>
                </section>

                <section class="space-y-2">
                  <h3 class="text-sm font-semibold text-highlighted">
                    System Instruction
                  </h3>
                  <UTextarea
                    v-model="customAgent.objective"
                    :maxlength="CUSTOM_LIMITS.objectiveChars"
                    :rows="3"
                    autoresize
                    placeholder="You are the support assistant for... Never reveal..."
                    class="w-full"
                  />
                  <p class="text-xs tabular-nums text-dimmed">
                    {{ customAgent.objective.length }} / {{ CUSTOM_LIMITS.objectiveChars }}
                  </p>
                </section>

                <section class="space-y-2">
                  <div class="flex items-end justify-between gap-2">
                    <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                      Tools
                      <UTooltip text="Use snake_case names. Calling a restricted tool counts as a leak.">
                        <UIcon
                          name="i-lucide-circle-question-mark"
                          class="size-3.5 text-dimmed"
                        />
                      </UTooltip>
                    </h3>
                    <UButton
                      label="Add tool"
                      icon="i-lucide-plus"
                      color="neutral"
                      variant="outline"
                      size="sm"
                      :disabled="customAgent.tools.length >= CUSTOM_LIMITS.tools"
                      @click="addCustomTool"
                    />
                  </div>
                  <ul
                    v-if="customAgent.tools.length > 0"
                    class="divide-y divide-default rounded-md border border-default"
                  >
                    <li
                      v-for="(tool, index) in customAgent.tools"
                      :key="index"
                      class="space-y-2 px-4 py-3"
                    >
                      <div class="flex items-center gap-2">
                        <UInput
                          v-model="tool.name"
                          :maxlength="CUSTOM_LIMITS.toolNameChars"
                          placeholder="lookup_order"
                          class="flex-1"
                        />
                        <USwitch
                          v-model="tool.allowed"
                          :label="tool.allowed ? 'Allowed' : 'Restricted'"
                        />
                        <UButton
                          icon="i-lucide-trash-2"
                          color="neutral"
                          variant="ghost"
                          size="sm"
                          :aria-label="`Remove tool ${index + 1}`"
                          @click="removeCustomTool(index)"
                        />
                      </div>
                      <UInput
                        v-model="tool.description"
                        :maxlength="CUSTOM_LIMITS.toolDescriptionChars"
                        placeholder="What the tool does"
                        class="w-full"
                      />
                    </li>
                  </ul>
                  <UEmpty
                    v-else
                    icon="i-lucide-wrench"
                    title="No tools yet"
                    description="Add the tools your agent can call."
                    size="sm"
                    variant="naked"
                  />
                  <p
                    v-for="message in customAgentErrors"
                    :key="message"
                    class="text-xs text-muted"
                  >
                    {{ message }}
                  </p>
                </section>

                <section class="space-y-2">
                  <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                    Dataset
                    <UTooltip text="Upload or paste CSV rows of text,label,expected_tool. Label is normal or attack; up to 50 rows.">
                      <UIcon
                        name="i-lucide-circle-question-mark"
                        class="size-3.5 text-dimmed"
                      />
                    </UTooltip>
                  </h3>
                  <div class="space-y-3 rounded-md border border-default p-3">
                    <UInput
                      type="file"
                      accept=".csv,.txt"
                      size="sm"
                      class="w-full"
                      @change="onCustomDatasetFile"
                    />
                    <UTextarea
                      v-model="customDatasetText"
                      :rows="5"
                      variant="none"
                      class="w-full"
                    />
                    <p class="text-xs tabular-nums text-dimmed">
                      {{ customDataset.summary || 'No valid rows yet' }}
                    </p>
                  </div>
                  <p
                    v-for="message in customDataset.errors"
                    :key="message"
                    class="text-xs text-muted"
                  >
                    {{ message }}
                  </p>
                  <ul
                    v-if="customDataset.rows.length > 0"
                    class="divide-y divide-default rounded-md border border-default"
                  >
                    <li
                      v-for="(row, index) in customDataset.rows.slice(0, 5)"
                      :key="index"
                      class="flex items-start gap-3 px-4 py-2"
                    >
                      <UBadge
                        :label="row.label === 'attack' ? 'Attack' : 'Normal'"
                        color="neutral"
                        :variant="row.label === 'attack' ? 'solid' : 'outline'"
                        size="sm"
                      />
                      <span class="line-clamp-2 min-w-0 flex-1 text-sm text-default">{{ row.text }}</span>
                    </li>
                  </ul>
                </section>
              </template>

              <section
                v-if="!isCustomMode"
                class="space-y-2"
              >
                <h3 class="text-sm font-semibold text-highlighted">
                  System Instruction
                </h3>
                <blockquote class="rounded-md border border-default bg-elevated/50 px-4 py-3 text-sm leading-relaxed text-default">
                  {{ levelAgent?.objective || 'Loading the level objective...' }}
                </blockquote>
              </section>

              <section
                v-if="!isCustomMode && levelAgent && levelAgent.tools.length > 0"
                class="space-y-2"
              >
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Tools
                  <UTooltip text="The agent may call allowed tools. Calling a restricted tool counts as a leak.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <ul class="divide-y divide-default rounded-md border border-default">
                  <li
                    v-for="tool in levelAgent.tools"
                    :key="tool.name"
                    class="flex items-start gap-3 px-4 py-3"
                  >
                    <UIcon
                      :name="tool.allowed ? 'i-lucide-wrench' : 'i-lucide-ban'"
                      class="mt-0.5 size-4 shrink-0 text-muted"
                    />
                    <div class="min-w-0 flex-1 space-y-0.5">
                      <p class="text-sm font-medium text-highlighted">
                        {{ formatToolName(tool.name) }}
                      </p>
                      <p class="text-sm text-muted">
                        {{ tool.description }}
                      </p>
                    </div>
                    <UBadge
                      :icon="tool.dual_use ? 'i-lucide-triangle-alert' : tool.allowed ? 'i-lucide-check' : 'i-lucide-x'"
                      :label="tool.dual_use ? 'Dual-Use' : tool.allowed ? 'Allowed' : 'Restricted'"
                      :color="tool.dual_use ? 'warning' : 'neutral'"
                      :variant="tool.allowed && !tool.dual_use ? 'outline' : 'subtle'"
                      size="sm"
                      class="shrink-0"
                    />
                  </li>
                </ul>
              </section>

              <section class="space-y-3">
                <div class="flex items-start justify-between gap-3">
                  <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                    Your rules
                    <UTooltip text="Added to the agent's instructions to keep it on task and resist prompt injection.">
                      <UIcon
                        name="i-lucide-circle-question-mark"
                        class="size-3.5 text-dimmed"
                      />
                    </UTooltip>
                  </h3>
                  <span class="shrink-0 text-xs tabular-nums text-dimmed">
                    {{ agentRules.length }} / {{ AGENT_RULE_LIMIT }}
                  </span>
                </div>

                <ol
                  v-if="agentRules.length > 0"
                  class="space-y-2"
                >
                  <li
                    v-for="(rule, index) in agentRules"
                    :key="index"
                    class="flex items-center gap-2"
                  >
                    <span class="flex size-6 shrink-0 items-center justify-center rounded-full border border-default text-xs tabular-nums text-muted">
                      {{ index + 1 }}
                    </span>
                    <UInput
                      :model-value="rule"
                      :maxlength="AGENT_RULE_MAX_CHARS"
                      class="flex-1"
                      :aria-label="`Rule ${index + 1}`"
                      @update:model-value="updateAgentRule(index, String($event))"
                    />
                    <UButton
                      icon="i-lucide-trash-2"
                      color="neutral"
                      variant="ghost"
                      :aria-label="`Remove rule ${index + 1}`"
                      @click="removeAgentRule(index)"
                    />
                  </li>
                </ol>
                <UEmpty
                  v-else
                  icon="i-lucide-list-checks"
                  title="No rules yet"
                  description="Without rules the agent relies on the objective alone."
                  size="sm"
                  variant="naked"
                />

                <div
                  v-if="canAddAgentRule(agentRules)"
                  class="space-y-2 rounded-md border border-default p-3"
                >
                  <UTextarea
                    v-model="ruleDraft"
                    :maxlength="AGENT_RULE_MAX_CHARS"
                    :rows="2"
                    autoresize
                    variant="none"
                    placeholder="Write a rule, for example: Never share discount codes."
                    class="w-full"
                    :disabled="!canAddAgentRule(agentRules)"
                    @keydown.enter.exact.prevent="addRuleFromDraft"
                  />
                  <div class="flex items-center justify-between gap-2">
                    <span class="text-xs tabular-nums text-dimmed">
                      {{ ruleDraft.length }} / {{ AGENT_RULE_MAX_CHARS }}
                    </span>
                    <UButton
                      label="Add rule"
                      icon="i-lucide-plus"
                      color="neutral"
                      variant="solid"
                      size="sm"
                      :disabled="!canAddAgentRule(agentRules) || !ruleDraft.trim()"
                      @click="addRuleFromDraft"
                    />
                  </div>
                </div>
              </section>
            </div>
          </template>

          <!-- Tool nodes: settings and outputs -->
          <template v-else>
            <div class="space-y-7">
              <section class="space-y-2">
                <h3 class="text-sm font-semibold text-highlighted">
                  What it does
                </h3>
                <blockquote class="rounded-md border border-default bg-elevated/50 px-4 py-3 text-sm leading-relaxed text-default">
                  {{ selectedCheck?.summary || selectedNode.data.subtitle }}
                </blockquote>
              </section>

              <!-- ML filter -->
              <section
                v-if="selectedNode.data.kind === 'ml_classifier'"
                class="space-y-4"
              >
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Model &amp; thresholds
                  <UTooltip text="Pick a classifier. Low risk passes, high risk is blocked, and anything between goes to Unclear on the board (leave Unclear unwired to stop it).">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <UFormField label="Algorithm">
                  <USelectMenu
                    :model-value="String(selectedNode.data.config.algorithm || 'tfidf')"
                    :items="mlAlgorithmItems"
                    value-key="value"
                    :search-input="false"
                    class="w-full"
                    @update:model-value="updateNodeConfig('algorithm', $event)"
                  />
                </UFormField>
                <div class="grid gap-3 sm:grid-cols-2">
                  <UFormField label="Pass below">
                    <UInputNumber
                      :model-value="Number(selectedNode.data.config.safe_threshold ?? 0.3)"
                      :min="0"
                      :max="Number(selectedNode.data.config.block_threshold ?? selectedNode.data.config.threshold ?? 0.75) - 0.05"
                      :step="0.05"
                      :format-options="{ style: 'percent' }"
                      class="w-full"
                      @update:model-value="updateNodeConfig('safe_threshold', $event)"
                    />
                  </UFormField>
                  <UFormField label="Block at or above">
                    <UInputNumber
                      :model-value="Number(selectedNode.data.config.block_threshold ?? selectedNode.data.config.threshold ?? 0.75)"
                      :min="Number(selectedNode.data.config.safe_threshold ?? 0.3) + 0.05"
                      :max="1"
                      :step="0.05"
                      :format-options="{ style: 'percent' }"
                      class="w-full"
                      @update:model-value="updateNodeConfig('block_threshold', $event)"
                    />
                  </UFormField>
                </div>
              </section>

              <section
                v-if="selectedNode.data.kind === 'ml_classifier'"
                class="space-y-3"
              >
                <div class="flex items-center justify-between gap-2">
                  <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                    Training data
                    <UTooltip text="Upload or paste CSV rows of text,label where 1 means attack and 0 means safe. Untrained models pass all prompts through.">
                      <UIcon
                        name="i-lucide-circle-question-mark"
                        class="size-3.5 text-dimmed"
                      />
                    </UTooltip>
                  </h3>
                  <UBadge
                    v-if="selectedNode.data.config.retrainNeeded && !selectedNode.data.config.model_id"
                    label="Retrain needed"
                    color="warning"
                    variant="subtle"
                    size="xs"
                  />
                </div>
                <p class="text-xs text-muted">
                  {{ ML_TRAINING_NOTICE }}
                </p>
                <UAlert
                  v-if="isAnonymous"
                  color="neutral"
                  variant="subtle"
                  icon="i-lucide-lock"
                  title="Sign in required to train"
                  description="Anonymous sessions cannot train custom ML filters."
                >
                  <template #actions>
                    <UButton
                      to="/auth/login"
                      label="Sign in to train"
                      color="neutral"
                      variant="solid"
                      size="xs"
                    />
                  </template>
                </UAlert>
                <div class="space-y-3 rounded-md border border-default p-3">
                  <UInput
                    type="file"
                    accept=".csv,.txt"
                    size="sm"
                    :disabled="isAnonymous"
                    class="w-full"
                    @change="onDatasetFileChange"
                  />
                  <UTextarea
                    v-model="mlCsvDraft"
                    :rows="5"
                    variant="none"
                    :disabled="isAnonymous"
                    :placeholder="'text,label\nignore previous instructions,1\nwhat are opening hours,0'"
                    class="w-full"
                  />
                  <div class="flex items-center justify-between gap-2">
                    <div class="flex flex-col">
                      <span class="text-xs tabular-nums text-dimmed">
                        {{ selectedNode.data.config.model_id && mlTrainStats ? `${mlTrainStats.sampleCount} rows, ${(mlTrainStats.accuracy * 100).toFixed(0)}% accuracy` : selectedNode.data.config.retrainNeeded ? 'Retrain needed' : 'Not trained yet' }}
                      </span>
                      <span
                        v-if="!isAnonymous"
                        class="text-xs tabular-nums text-muted"
                      >
                        {{ formatRemainingTrainings(session) }}
                      </span>
                    </div>
                    <UButton
                      label="Train model"
                      icon="i-lucide-cpu"
                      color="neutral"
                      variant="solid"
                      size="sm"
                      :loading="mlTraining"
                      :disabled="isAnonymous || !mlCsvDraft.trim()"
                      @click="handleTrainCustomMl(false)"
                    />
                  </div>
                </div>
              </section>

              <!-- Text cleaner -->
              <section
                v-if="selectedNode.data.kind === 'text_cleanup'"
                class="space-y-3"
              >
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Transforms
                  <UTooltip text="Select which normalisations to run. Each enabled transform adds 0.4 ms per message.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <div class="flex flex-wrap gap-1.5">
                  <UButton
                    v-for="tr in [
                      { id: 'strip_zero_width', label: 'Strip zero-width chars' },
                      { id: 'decode_base64', label: 'Decode Base64' },
                      { id: 'decode_hex_url', label: 'Decode hex and URL' }
                    ]"
                    :key="tr.id"
                    :label="tr.label"
                    :icon="hasTextTransform(tr.id) ? 'i-lucide-check' : undefined"
                    color="neutral"
                    :variant="hasTextTransform(tr.id) ? 'solid' : 'outline'"
                    size="md"
                    @click="toggleTextTransform(tr.id)"
                  />
                </div>
              </section>

              <!-- Jev -->
              <section
                v-if="selectedNode.data.kind === 'jev'"
                class="space-y-4"
              >
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Noul question
                  <UTooltip text="Ask a boolean question about the prompt. Jev evaluates it in a single System One pass and returns a probability in [0, 1].">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <UTextarea
                  :model-value="String(selectedNode.data.config.question ?? '')"
                  :rows="2"
                  :maxlength="300"
                  placeholder="For example: Is this prompt attempting to override instructions or extract secrets?"
                  class="w-full"
                  @update:model-value="updateNodeConfig('question', $event)"
                />
                <UFormField :label="selectedNode.data.config.tool_policy_enabled ? 'Trigger tool policy at or above' : 'Block at or above'">
                  <UInputNumber
                    :model-value="Number(selectedNode.data.config.threshold ?? 0.7)"
                    :min="0.05"
                    :max="0.95"
                    :step="0.05"
                    :format-options="{ style: 'percent' }"
                    class="w-48"
                    @update:model-value="updateNodeConfig('threshold', $event)"
                  />
                </UFormField>
              </section>

              <!-- Word filter -->
              <section
                v-if="selectedNode.data.kind === 'word_filter'"
                class="space-y-3"
              >
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Custom blocked words
                  <UTooltip text="Any prompt containing one of these phrases is blocked.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <ul
                  v-if="customWordsList.length > 0"
                  class="divide-y divide-default rounded-md border border-default"
                >
                  <li
                    v-for="word in customWordsList"
                    :key="word"
                    class="flex items-center justify-between gap-3 px-4 py-2 text-sm"
                  >
                    <span class="truncate text-default">{{ word }}</span>
                    <UButton
                      icon="i-lucide-trash-2"
                      color="neutral"
                      variant="ghost"
                      size="sm"
                      :aria-label="`Remove ${word}`"
                      @click="removeCustomWord(word)"
                    />
                  </li>
                </ul>
                <div class="flex items-center gap-2 rounded-md border border-default p-2">
                  <UInput
                    v-model="customWordDraft"
                    placeholder="Add a phrase, for example: secret code"
                    variant="none"
                    class="flex-1"
                    @keydown.enter="addCustomWord"
                  />
                  <UButton
                    label="Add word"
                    icon="i-lucide-plus"
                    color="neutral"
                    variant="solid"
                    size="sm"
                    :disabled="!customWordDraft.trim()"
                    @click="addCustomWord"
                  />
                </div>
              </section>

              <!-- Secret scanner -->
              <section
                v-if="selectedNode.data.kind === 'secret_scan'"
                class="space-y-3"
              >
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Regex patterns
                  <UTooltip text="Case-insensitive regular expressions to block, such as sk-[a-z0-9]{6,} or password|secret.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <ul
                  v-if="secretPatternsList.length > 0"
                  class="divide-y divide-default rounded-md border border-default"
                >
                  <li
                    v-for="pattern in secretPatternsList"
                    :key="pattern"
                    class="flex items-center justify-between gap-3 px-4 py-2 text-sm"
                  >
                    <span class="truncate text-default">{{ pattern }}</span>
                    <UButton
                      icon="i-lucide-trash-2"
                      color="neutral"
                      variant="ghost"
                      size="sm"
                      :aria-label="`Remove ${pattern}`"
                      @click="removeSecretPattern(pattern)"
                    />
                  </li>
                </ul>
                <div class="flex items-center gap-2 rounded-md border border-default p-2">
                  <UInput
                    v-model="secretPatternDraft"
                    placeholder="Add a regex, for example: password|secret\s+code"
                    variant="none"
                    class="flex-1"
                    @keydown.enter="addSecretPattern"
                  />
                  <UButton
                    label="Add regex"
                    icon="i-lucide-plus"
                    color="neutral"
                    variant="solid"
                    size="sm"
                    :disabled="!secretPatternDraft.trim()"
                    @click="addSecretPattern"
                  />
                </div>
              </section>

              <!-- Length limit -->
              <section
                v-if="selectedNode.data.kind === 'length_limit'"
                class="space-y-3"
              >
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Maximum length
                  <UTooltip text="Prompts longer than this are blocked before they can stuff the context.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <UFormField label="Characters">
                  <UInputNumber
                    :model-value="Number(selectedNode.data.config.max_chars ?? 240)"
                    :min="20"
                    :max="4000"
                    :step="20"
                    class="w-48"
                    @update:model-value="updateNodeConfig('max_chars', $event)"
                  />
                </UFormField>
              </section>

              <!-- Safety check: dedicated safety/guardrail models only -->
              <section
                v-if="selectedNode.data.kind === 'safety_check'"
                class="space-y-3"
              >
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Safety guardrail model
                  <UTooltip text="Only safety-specific guardrail models are available for Safety check.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <USelectMenu
                  :model-value="String(selectedNode.data.config.model || DEFAULT_SAFETY_CHECK_MODEL)"
                  :items="safetyCheckModelItems"
                  value-key="value"
                  class="w-full"
                  @update:model-value="updateNodeConfig('model', $event)"
                />
                <USwitch
                  v-if="nodeSupportsThinking(selectedNode.data.kind, String(selectedNode.data.config.model || DEFAULT_SAFETY_CHECK_MODEL))"
                  color="neutral"
                  :model-value="Boolean(selectedNode.data.config.thinking)"
                  label="Thinking"
                  description="The model reasons before it answers. It catches more attacks but costs more tokens and time."
                  @update:model-value="updateNodeConfig('thinking', Boolean($event))"
                />
              </section>

              <!-- Tool policy extension for Jev and Safety check -->
              <section
                v-if="selectedNode.data.kind === 'jev' || selectedNode.data.kind === 'safety_check'"
                class="space-y-3"
              >
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Tool policy
                  <UTooltip text="When enabled, triggering this node switches off the selected tools on the final LangGraph agent and lets the prompt pass.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <div class="space-y-3">
                  <USwitch
                    color="neutral"
                    :model-value="Boolean(selectedNode.data.config.tool_policy_enabled)"
                    label="Switch off agent tools instead of blocking prompt"
                    @update:model-value="updateNodeConfig('tool_policy_enabled', Boolean($event))"
                  />
                  <div
                    v-if="Boolean(selectedNode.data.config.tool_policy_enabled)"
                    class="space-y-2 pt-3"
                  >
                    <div
                      v-if="numberedAgentTools.length > 0"
                      class="grid gap-2 sm:grid-cols-2"
                    >
                      <UCheckbox
                        v-for="item in numberedAgentTools"
                        :key="item.index"
                        color="neutral"
                        :model-value="hasBlockedToolIndex(item.index, item.name)"
                        :label="item.label"
                        @update:model-value="toggleBlockedToolIndex(item.index, item.name)"
                      />
                    </div>
                    <p
                      v-else
                      class="text-xs text-muted"
                    >
                      This level has no final agent tools to switch off.
                    </p>
                  </div>
                </div>
              </section>

              <!-- LLM review: general LLM + custom review instructions + dynamic tool policy -->
              <section
                v-if="selectedNode.data.kind === 'llm_review'"
                class="space-y-4"
              >
                <div class="space-y-2">
                  <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                    Reviewer model
                    <UTooltip text="General-purpose LLM used to review suspicious prompts.">
                      <UIcon
                        name="i-lucide-circle-question-mark"
                        class="size-3.5 text-dimmed"
                      />
                    </UTooltip>
                  </h3>
                  <USelectMenu
                    :model-value="String(selectedNode.data.config.model || DEFAULT_LLM_REVIEW_MODEL)"
                    :items="llmReviewModelItems"
                    value-key="value"
                    class="w-full"
                    @update:model-value="updateNodeConfig('model', $event)"
                  />
                  <USwitch
                    v-if="nodeSupportsThinking(selectedNode.data.kind, String(selectedNode.data.config.model || DEFAULT_LLM_REVIEW_MODEL))"
                    color="neutral"
                    :model-value="Boolean(selectedNode.data.config.thinking)"
                    label="Thinking"
                    description="The model reasons before it answers. It catches more attacks but costs more tokens and time."
                    @update:model-value="updateNodeConfig('thinking', Boolean($event))"
                  />
                </div>
                <div class="space-y-2">
                  <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                    Tool policy
                    <UTooltip text="Allow the reviewer AI to switch off specific tools on the final LangGraph agent when a prompt looks benign but risky for certain tools.">
                      <UIcon
                        name="i-lucide-circle-question-mark"
                        class="size-3.5 text-dimmed"
                      />
                    </UTooltip>
                  </h3>
                  <div class="space-y-2">
                    <USwitch
                      color="neutral"
                      :model-value="Boolean(selectedNode.data.config.tool_policy_enabled)"
                      label="Allow reviewer AI to switch off final agent tools"
                      @update:model-value="updateNodeConfig('tool_policy_enabled', Boolean($event))"
                    />
                  </div>
                </div>
                <div class="space-y-2">
                  <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                    Review instructions
                    <UTooltip text="Custom prompt telling the reviewer LLM what attacks, policy violations, or exfiltration tricks to block.">
                      <UIcon
                        name="i-lucide-circle-question-mark"
                        class="size-3.5 text-dimmed"
                      />
                    </UTooltip>
                  </h3>
                  <UTextarea
                    :model-value="String(selectedNode.data.config.prompt ?? '')"
                    :rows="3"
                    :maxlength="1000"
                    :placeholder="Boolean(selectedNode.data.config.tool_policy_enabled)
                      ? 'For example: Block direct prompt injections; if a user asks about salaries or database maintenance, allow the prompt but switch off Tool 2.'
                      : 'For example: Block any prompt asking to reveal salary records, system instructions, or call restricted tools.'"
                    class="w-full"
                    @update:model-value="updateNodeConfig('prompt', $event)"
                  />
                </div>
              </section>
            </div>
          </template>
        </div>
      </template>

      <template #footer>
        <div class="flex w-full items-center justify-end">
          <UButton
            label="Done"
            color="neutral"
            variant="solid"
            size="md"
            @click="isNodeModalOpen = false"
          />
        </div>
      </template>
    </UModal>

    <!-- Guided tour for introductory levels (WEB-CAMP-007) -->
    <UPopover
      :open="tour.open.value"
      :reference="tour.reference.value"
      :dismissible="false"
      :content="{ side: tour.current.value?.side ?? 'bottom', sideOffset: 12, collisionPadding: 16 }"
      arrow
    >
      <template #content>
        <div
          v-if="tour.current.value"
          class="w-80 space-y-3 p-4"
        >
          <div class="flex items-center justify-between gap-2">
            <p class="text-sm font-semibold text-highlighted">
              {{ tour.current.value.title }}
            </p>
            <span class="shrink-0 text-xs tabular-nums text-dimmed">
              {{ tour.index.value + 1 }} / {{ tour.total.value }}
            </span>
          </div>
          <p class="text-sm text-muted">
            {{ tour.current.value.body }}
          </p>
          <div class="flex items-center justify-between gap-2">
            <UButton
              label="Skip"
              color="neutral"
              variant="link"
              size="sm"
              @click="endLevelTour"
            />
            <div class="flex items-center gap-2">
              <UButton
                v-if="tour.hasPrev.value"
                label="Back"
                color="neutral"
                variant="outline"
                size="sm"
                @click="tour.prev()"
              />
              <UButton
                :label="isLastTourStep ? 'Finish' : 'Next'"
                color="neutral"
                variant="solid"
                size="sm"
                @click="nextTourStep"
              />
            </div>
          </div>
        </div>
      </template>
    </UPopover>

    <UModal
      v-model:open="isReplaceModelConfirmOpen"
      title="Replace earlier trained model?"
      :description="REPLACE_MODEL_WARNING"
    >
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            label="Cancel"
            color="neutral"
            variant="ghost"
            @click="isReplaceModelConfirmOpen = false"
          />
          <UButton
            label="Train & replace"
            color="neutral"
            variant="solid"
            @click="handleTrainCustomMl(true)"
          />
        </div>
      </template>
    </UModal>
  </div>
</template>
