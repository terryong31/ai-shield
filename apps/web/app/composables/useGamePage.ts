/**
 * State and logic of the game page (spec 0055). `pages/game.vue` calls it once and
 * provides it; the panels under `components/game/` read it with `useGameContext()`.
 */
import { computed, inject, nextTick, onMounted, ref, shallowRef, watch, type InjectionKey, type Ref } from 'vue'
import { useVueFlow, type Connection, type Edge, type EdgeChange, type Node, type NodeChange, type NodeMouseEvent } from '@vue-flow/core'
import { CUSTOM_LIMITS, OBJECTIVE_REQUIRED, customFormSchema, readDatasetFile, PROVIDER_OPTIONS, customModeAccess, datasetRowsToCsv, parseDatasetCsv, validateCustomAgent, type CustomAgent, type ProviderId } from '~/utils/customSandbox'
import type { CheckDefinitionSchema, GameLevelSchema, LevelId, MessageTraceSchema, NodeKind, RunStopSchema, SavedBoardRequest, WaveScoreSchema } from '~/types/api'
import { AGENT_RULE_MAX_CHARS, NODE_CATALOG, SAFETY_CHECK_MODELS, LLM_REVIEW_MODELS, addAgentRule, addCheckNode, agentRulesFrom, applyWaveSummary, canAddAgentRule, canUseNodeKind, nodeKeyRequirement, connectBoardEdge, createStarterBoard, formatToolName, FINAL_NODE_LABELS, isClassifyOnlyLevel, isValidLevelId, markBoardRunning, nodeCostLine, removeBoardNode, resetBoardStatuses, attemptsLeftLabel, nextHighScore, isNewRecord, nextHighStars, waveStars, toApiBoard, boardFromSave, boardSignature, saveFromBoard, type GameNodeData, confusionMatrix, runWithAnonymousRetry } from '~/utils/gameBoard'
import { FALLBACK_CAMPAIGN_LEVELS, canAccessLevel, levelHighScore, countPlacedCheckNodes, isCheckDisabledByConstraints, nextCampaignLevel } from '~/utils/campaignSelect'
import { hasSeenTour, levelTourSteps, markTourSeen } from '~/utils/levelTours'
import { DRAFT_DEBOUNCE_MS, browserDraftStorage, draftPromotion, readDraft, removeDraft, writeDraft } from '~/utils/anonDraft'
import { applyTrainedModelToBoard, checkTrainingFile, decodeTrainingCsv, markUntrainedModelNodes, needsReplaceConfirmation, triggerBeaconPurge } from '~/utils/mlTraining'

/** The parts of the custom sandbox UForm that the page calls. */
interface CustomFormHandle {
  validate: (opts: { name: string, silent: boolean }) => Promise<unknown>
  setErrors: (errors: Array<{ name: string, message: string }>, name: string) => void
}

export function useGamePage() {
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
  const customDatasetText = ref('')
  const customDataset = computed(() =>
    parseDatasetCsv(customDatasetText.value, customAgent.value.tools.map(t => t.name))
  )
  const customFormSchemaFor = computed(() => customFormSchema(customAgent.value.tools.map(t => t.name)))
  const customFormState = computed(() => ({ objective: customAgent.value.objective, dataset: customDatasetText.value }))
  // Set by the custom sandbox form in the node settings modal (ref="customForm").
  const customForm = shallowRef<CustomFormHandle | null>(null)
  const revalidateDataset = async () => {
    await nextTick()
    if (customDatasetText.value.trim()) await customForm.value?.validate({ name: 'dataset', silent: true })
  }
  watch(() => customAgent.value.tools.map(t => t.name).join(','), revalidateDataset)
  const customAgentErrors = computed(() => validateCustomAgent(customAgent.value).filter(e => e !== OBJECTIVE_REQUIRED))
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
    const result = await readDatasetFile(file)
    if ('error' in result) {
      customForm.value?.setErrors([{ name: 'dataset', message: result.error }], 'dataset')
      return
    }
    customDatasetText.value = result.text
    await revalidateDataset()
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
  // Set when a time limit or the cost budget stopped the last run (WEB-FAIR-003).
  const runStop = ref<RunStopSchema | null>(null)
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
        final_node_label: 'Protected Agent',
        new_idea: '',
        briefing: [],
        version: 1
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
      title: isEasy ? 'Public Helpdesk' : isMedium ? 'HR Handbook' : 'Warehouse',
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
      final_node_label: FINAL_NODE_LABELS[currentLevelId.value],
      new_idea: '',
      briefing: [],
      version: 1
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
    runStop.value = null
    selectedNodeId.value = null
    isNodeModalOpen.value = false
  }

  // Restart also forgets the anonymous draft of this level (WEB-DRAFT-002).
  const handleRestart = () => {
    resetBoard()
    removeDraft(browserDraftStorage(), currentLevelId.value)
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

  // A free hint with the wave's attack examples (WEB-LADDER-003).
  const isHintOpen = ref(false)
  const hasLevelHint = computed(() => !isCustomMode.value && (currentLevel.value.briefing?.length ?? 0) > 0)

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

  const trainingError = (description: string) => {
    toast.add({ title: 'Training error', description, icon: 'i-lucide-triangle-alert', color: 'neutral' })
  }

  const onDatasetFileChange = async (event: Event) => {
    if (isAnonymous.value) return
    const target = event.target as { files?: FileList | null } | null
    const file = target?.files?.[0]
    if (!file) return
    const sizeCheck = checkTrainingFile(file, isCustomMode.value ? 'custom' : 'campaign')
    if (!sizeCheck.ok) {
      trainingError(sizeCheck.error)
      return
    }
    const buffer = await file.arrayBuffer()
    const decoded = decodeTrainingCsv(buffer)
    if (!decoded.ok) {
      trainingError(decoded.error)
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
      trainingError(msg)
    } finally {
      mlTraining.value = false
    }
  }

  const selectedCheck = computed(() =>
    checks.value.find(c => c.kind === selectedNode.value?.data?.kind) ?? null
  )

  // The final node's job, shown under its modal title on every level (WEB-LEVEL-005).
  const FINAL_NODE_HINT = 'This is the agent you need to protect. Only let safe prompts get through here.'

  const nodeModalDescription = computed(() => {
    const data = selectedNode.value?.data
    if (!data) return ''
    if (data.kind === 'assistant') return FINAL_NODE_HINT
    return nodeCostLine(
      selectedCheck.value?.latency_ms ?? data.latencyMs,
      selectedCheck.value?.cost_usd ?? data.costUsd
    )
  })

  // The board name of a node, for result rows and the stop path.
  const nodeLabel = (nodeId: string): string => {
    const node = nodes.value.find(n => n.id === nodeId)
    const label = node?.data?.label
    return typeof label === 'string' && label ? label : nodeId
  }

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

  // Anonymous drafts (spec 0052): the level whose draft was read, so a board is
  // written back only after its own draft loaded, and never after a sign-out.
  const draftReadyLevel = ref<LevelId | null>(null)
  const pendingDraft = ref<SavedBoardRequest | null>(null)
  const isDraftConflictOpen = ref(false)
  let draftTimer: ReturnType<typeof setTimeout> | undefined

  watch(isAnonymous, () => {
    draftReadyLevel.value = null
  })

  watch(currentSignature, () => {
    clearTimeout(draftTimer)
    if (!isAnonymous.value || isCustomMode.value || draftReadyLevel.value !== currentLevelId.value) return
    const levelId = currentLevelId.value
    // The board is read once, when the debounce window ends.
    draftTimer = setTimeout(() => {
      if (isAnonymous.value && draftReadyLevel.value === currentLevelId.value && levelId === currentLevelId.value) {
        writeDraft(browserDraftStorage(), levelId, saveFromBoard({ nodes: nodes.value, edges: edges.value }))
      }
    }, DRAFT_DEBOUNCE_MS)
  })

  const loadAnonymousDraft = () => {
    if (isCustomMode.value) return
    const levelId = currentLevelId.value
    const draft = readDraft(browserDraftStorage(), levelId)
    if (draft.kind === 'ok') {
      applySavePayload(draft.save)
    } else if (draft.kind === 'invalid') {
      removeDraft(browserDraftStorage(), levelId)
      toast.add({
        title: 'Your local board could not be loaded',
        description: 'The starter board is shown.',
        icon: 'i-lucide-triangle-alert',
        color: 'neutral'
      })
    }
    draftReadyLevel.value = levelId
  }

  const keepDraftWarning = () => {
    toast.add({
      title: 'Your local board is not saved to your account yet',
      description: 'It stays in this browser. Try again later.',
      icon: 'i-lucide-triangle-alert',
      color: 'neutral'
    })
  }

  // Upload a local draft to the account; on failure the draft stays in the browser.
  const uploadDraft = async (levelId: LevelId, draft: SavedBoardRequest) => {
    try {
      await putSave(levelId, draft)
    } catch {
      keepDraftWarning()
      return
    }
    setCachedBoard(saveOwnerKey.value, levelId, draft)
    removeDraft(browserDraftStorage(), levelId)
    if (levelId === currentLevelId.value) {
      applySavePayload(draft)
      markSaved()
    }
    toast.add({ title: 'Your local board was saved to your account.', icon: 'i-lucide-check', color: 'neutral' })
  }

  // After sign-in, move this level's anonymous draft to the account (WEB-DRAFT-004 to 006).
  const promoteDraft = async (status: number | null) => {
    if (isCustomMode.value) return
    const levelId = currentLevelId.value
    const draft = readDraft(browserDraftStorage(), levelId)
    if (draft.kind === 'invalid') removeDraft(browserDraftStorage(), levelId)
    if (draft.kind !== 'ok') return
    const action = draftPromotion(status)
    if (action === 'discard') {
      removeDraft(browserDraftStorage(), levelId)
    } else if (action === 'keep') {
      keepDraftWarning()
    } else if (action === 'prompt') {
      pendingDraft.value = draft.save
      isDraftConflictOpen.value = true
    } else {
      await uploadDraft(levelId, draft.save)
    }
  }

  const keepLocalBoard = async () => {
    const draft = pendingDraft.value
    isDraftConflictOpen.value = false
    pendingDraft.value = null
    if (!draft) return
    await uploadDraft(currentLevelId.value, draft)
  }

  const useSavedBoard = () => {
    removeDraft(browserDraftStorage(), currentLevelId.value)
    pendingDraft.value = null
    isDraftConflictOpen.value = false
  }

  const loadSavedBoard = async () => {
    if (isAnonymous.value) {
      loadAnonymousDraft()
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
    let saveStatus: number | null
    try {
      const save = await getSave(saveLevelKey.value)
      saveStatus = 200
      setCachedBoard(saveOwnerKey.value, saveLevelKey.value, save)
      if (!cached || JSON.stringify(save.board) !== JSON.stringify(cached.board) || JSON.stringify(save.positions) !== JSON.stringify(cached.positions)) {
        applySavePayload(save)
      }
    } catch (err) {
      saveStatus = (err as { statusCode?: number }).statusCode ?? null
      if (saveStatus !== 404) {
        console.warn('Saved board unavailable:', err)
      }
    } finally {
      isLoadingBoard.value = false
    }
    markSaved()
    await promoteDraft(saveStatus)
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
      runStop.value = response.stop ?? null
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

  return {
    isCustomMode,
    customAgent,
    customProvider,
    customModel,
    customApiKey,
    customDatasetText,
    customDataset,
    customForm,
    customFormSchemaFor,
    customFormState,
    customAgentErrors,
    providerItems,
    addCustomTool,
    removeCustomTool,
    onCustomDatasetFile,
    currentLevelId,
    isBriefingOpen,
    checks,
    nodes,
    edges,
    isNodeModalOpen,
    isQuitModalOpen,
    isSidebarCollapsed,
    toolCardUi,
    selectedNode,
    runningWave,
    traces,
    waveScore,
    runStop,
    highScore,
    newRecord,
    highStars,
    customMessage,
    customWordDraft,
    secretPatternDraft,
    nodeKeyState,
    mlCsvDraft,
    mlTraining,
    mlTrainStats,
    isReplaceModelConfirmOpen,
    mlAlgorithmItems,
    safetyCheckModelItems,
    llmReviewModelItems,
    currentLevel,
    levelAgent,
    isProLevelLocked,
    placedCheckNodeCount,
    maxCheckNodes,
    nextLevel,
    FLOW_ID,
    onNodesChange,
    onEdgesChange,
    handleRestart,
    handleReturnClick,
    confirmQuitToMenu,
    isToolLocked,
    hasLevelTour,
    isHintOpen,
    hasLevelHint,
    tour,
    isLastTourStep,
    startLevelTour,
    endLevelTour,
    nextTourStep,
    handlePlaceCheck,
    onToolDragStart,
    onCanvasDragOver,
    onCanvasDrop,
    isToolInfoOpen,
    infoTool,
    openToolInfo,
    onNodeClick,
    onNodeDoubleClick,
    onConnect,
    updateNodeConfig,
    customWordsList,
    addCustomWord,
    removeCustomWord,
    secretPatternsList,
    addSecretPattern,
    removeSecretPattern,
    hasTextTransform,
    toggleTextTransform,
    numberedAgentTools,
    hasBlockedToolIndex,
    toggleBlockedToolIndex,
    onDatasetFileChange,
    handleTrainCustomMl,
    selectedCheck,
    nodeModalDescription,
    nodeLabel,
    isResultsOpen,
    resultCells,
    isBreakdownOpen,
    breakdownAccordionItems,
    isResultCellOpen,
    selectedResultCell,
    openResultCell,
    agentRules,
    ruleDraft,
    addRuleFromDraft,
    updateAgentRule,
    removeAgentRule,
    isSignInPromptOpen,
    openSignInPrompt,
    showAttempts,
    savingBoard,
    isLoadingBoard,
    hasUnsavedChanges,
    handleSaveBoard,
    isDraftConflictOpen,
    keepLocalBoard,
    useSavedBoard,
    handleRunWave,
    handleTestCustomMessage,
    session,
    isAnonymous,
    isLoggedIn,
    isPaid
  }
}

export type GamePage = ReturnType<typeof useGamePage>

export const GAME_PAGE: InjectionKey<GamePage> = Symbol('game-page')

/** The game page state, for the panels of `pages/game.vue`. */
export function useGameContext(): GamePage {
  const page = inject(GAME_PAGE)
  if (!page) throw new Error('useGameContext() needs the game page, which provides it.')
  return page
}
