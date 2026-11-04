// Pure NDJSON parsing and event folding for the /chat stream (spec 0008 and spec 0013).
// Kept free of Vue and Nuxt so it can be unit-tested in plain Vitest.
import type { ChatEvent, DecisionLayer } from '../types/api'
import type { ShieldMetadata, WorkflowState } from '../types/workflow'

export interface NdjsonChunk {
  events: ChatEvent[]
  errors: string[]
  rest: string
}

/** Split complete lines off `buffer`; the trailing partial line is returned as `rest`. */
export function splitNdjson(buffer: string): { lines: string[], rest: string } {
  const parts = buffer.split('\n')
  const rest = parts.pop() ?? ''
  return { lines: parts.map(line => line.trim()).filter(Boolean), rest }
}

/** Parse every complete line; malformed lines are reported, never thrown. */
export function parseNdjson(buffer: string): NdjsonChunk {
  const { lines, rest } = splitNdjson(buffer)
  const events: ChatEvent[] = []
  const errors: string[] = []
  for (const line of lines) {
    try {
      events.push(JSON.parse(line) as ChatEvent)
    } catch {
      errors.push(line)
    }
  }
  return { events, errors, rest }
}

export interface ChatTurn {
  workflow: WorkflowState
  metadata: ShieldMetadata
  text: string
  startedAt?: number
}

export const STAGE_LABEL: Record<DecisionLayer, string> = {
  LAYER_1_ML: 'screening',
  LAYER_2_DUAL_AGENT: 'agent review',
  SYSTEM: 'system check'
}

export const shutdownNotice = (reason: string, layer: DecisionLayer = 'LAYER_1_ML'): string =>
  `Blocked during ${STAGE_LABEL[layer] ?? 'screening'}. ${reason}`

function summarizeEvent(event: ChatEvent): string {
  switch (event.type) {
    case 'START':
      return 'Message received'
    case 'STAGE_CHANGE':
      return `Stage: ${event.stage}`
    case 'ML_RESULT':
      return `${event.verdict} (${(event.confidence * 100).toFixed(1)}%)`
    case 'LLAMAGUARD_RESULT':
      return event.safe ? 'Safety check passed' : `Flagged: ${event.categories.join(', ')}`
    case 'DEBATE_TURN':
      return `${event.agent}: ${event.message}`
    case 'POLICY_UPDATE':
      return `Policy: ${event.policy}`
    case 'TOOL_START':
      return `Tool: ${event.tool}`
    case 'TOOL_END':
      return `Completed: ${event.tool}`
    case 'BLOCK':
      return shutdownNotice(event.reason, event.layer)
    case 'FINAL_RESPONSE':
      return 'Response ready'
    case 'ERROR':
      return `Error: ${event.message}`
  }
}

/** Fold one stream event into the turn's state, returning a new state. */
export function applyChatEvent(
  turn: ChatTurn,
  event: ChatEvent,
  now?: number,
  fromReduce?: unknown
): ChatTurn {
  const hasExplicitTimestamp = typeof now === 'number' && fromReduce === undefined
  const workflow: WorkflowState = {
    ...turn.workflow,
    activeTools: [...turn.workflow.activeTools],
    debate: [...(turn.workflow.debate ?? [])],
    timeline: [...(turn.workflow.timeline ?? [])]
  }
  const metadata: ShieldMetadata = { ...turn.metadata }
  let text = turn.text
  let startedAt = turn.startedAt

  if (event.type === 'START' && hasExplicitTimestamp) {
    startedAt = now
  }

  const offset = hasExplicitTimestamp && startedAt !== undefined ? now - startedAt : null
  workflow.timeline?.push({
    type: event.type,
    at: offset,
    summary: summarizeEvent(event)
  })

  switch (event.type) {
    case 'START':
      workflow.query = event.query
      break
    case 'STAGE_CHANGE':
      workflow.stage = event.stage
      break
    case 'ML_RESULT':
      workflow.mlConfidence = event.confidence
      workflow.mlVerdict = event.verdict
      metadata.mlConfidence = event.confidence
      break
    case 'LLAMAGUARD_RESULT':
      workflow.moderation = {
        safe: event.safe,
        categories: [...event.categories]
      }
      break
    case 'DEBATE_TURN':
      workflow.lastAgentMessage = `${event.agent}: ${event.message}`
      workflow.dualAgentTriggered = true
      workflow.debate = [...(workflow.debate ?? []), { agent: event.agent, message: event.message }]
      metadata.dualAgentTriggered = true
      break
    case 'POLICY_UPDATE':
      workflow.toolPolicy = event.policy
      metadata.toolPolicy = event.policy
      metadata.allowedTools = event.allowed_tools
      break
    case 'TOOL_START':
      workflow.activeTools = [...workflow.activeTools, event.tool]
      break
    case 'BLOCK':
      workflow.blocked = true
      workflow.blockedLayer = event.layer
      metadata.blocked = true
      metadata.reason = event.reason
      text = shutdownNotice(event.reason, event.layer)
      break
    case 'FINAL_RESPONSE':
      text = event.text
      break
    case 'ERROR':
      text = `Error: ${event.message}`
      break
    default:
      break
  }

  return startedAt !== undefined
    ? { workflow, metadata, text, startedAt }
    : { workflow, metadata, text }
}
