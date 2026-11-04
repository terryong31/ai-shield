import type { ChatEvent, DecisionLayer, SecurityMode, ToolPolicy, Verdict } from './api'

export type WorkflowStage = 'idle' | 'start' | 'ml_processing' | 'debate' | 'dual_agent' | 'final' | 'complete'

export interface DebateEntry {
  agent: 'ANALYST' | 'WARDEN'
  message: string
}

export interface TimelineEntry {
  type: ChatEvent['type']
  at: number | null
  summary: string
}

export interface ModerationState {
  safe: boolean
  categories: string[]
}

export interface WorkflowState {
  query: string
  stage: WorkflowStage
  mlConfidence: number | null
  mlVerdict: Verdict | ''
  lastAgentMessage: string
  dualAgentTriggered: boolean
  blocked: boolean
  toolPolicy?: ToolPolicy
  activeTools: string[]
  mode: SecurityMode
  moderation?: ModerationState | null
  debate?: DebateEntry[]
  timeline?: TimelineEntry[]
  blockedLayer?: DecisionLayer
}

/** Per-message badges shown under an assistant reply. */
export interface ShieldMetadata {
  blocked?: boolean
  reason?: string
  toolPolicy?: ToolPolicy
  mlConfidence?: number | null
  dualAgentTriggered?: boolean
  allowedTools?: string[]
}
