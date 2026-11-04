import type { WorkflowState } from '../types/workflow'

export type NodeStatus = 'idle' | 'active' | 'passed' | 'flagged' | 'blocked' | 'skipped'
export type PipelineNodeId
  = | 'input'
    | 'classifier'
    | 'moderation'
    | 'router'
    | 'adjudication'
    | 'assistant'
    | 'tools'
    | 'blocked'

export interface PipelineNodeView {
  id: PipelineNodeId
  status: NodeStatus
  datum?: string
}

export interface PipelineGraph {
  nodes: PipelineNodeView[]
  activeEdges: string[]
  traversedEdges: string[]
}

const APPEARANCE: Record<NodeStatus, { icon: string, label: string, class: string }> = {
  idle: {
    icon: 'i-lucide-circle-dashed',
    label: 'Idle',
    class: 'border-dashed border-default text-dimmed'
  },
  active: {
    icon: 'i-lucide-loader-circle',
    label: 'Running',
    class: 'border-solid border-default text-highlighted'
  },
  passed: {
    icon: 'i-lucide-check',
    label: 'Passed',
    class: 'border-solid border-default text-default'
  },
  flagged: {
    icon: 'i-lucide-triangle-alert',
    label: 'Flagged',
    class: 'border-solid border-accented bg-elevated text-highlighted'
  },
  blocked: {
    icon: 'i-lucide-shield-x',
    label: 'Blocked',
    class: 'border-solid border-inverted bg-inverted text-inverted'
  },
  skipped: {
    icon: 'i-lucide-minus',
    label: 'Skipped',
    class: 'border-dashed border-default opacity-50 text-dimmed'
  }
}

export function statusAppearance(status: NodeStatus): { icon: string, label: string, class: string } {
  return APPEARANCE[status]
}

export function derivePipelineGraph(state: WorkflowState): PipelineGraph {
  const isIdle = state.stage === 'idle' || (state.stage === 'start' && !state.mlVerdict && !state.moderation && !state.blocked)
  if (isIdle) {
    return {
      nodes: [
        { id: 'input', status: 'idle' },
        { id: 'classifier', status: 'idle' },
        { id: 'moderation', status: 'idle' },
        { id: 'router', status: 'idle' },
        { id: 'adjudication', status: 'idle' },
        { id: 'assistant', status: 'idle' },
        { id: 'tools', status: 'idle' },
        { id: 'blocked', status: 'idle' }
      ],
      activeEdges: [],
      traversedEdges: []
    }
  }

  const activeEdges: string[] = []
  const traversedEdges: string[] = ['e-input-classifier']

  let classifierStatus: NodeStatus = 'passed'
  if (state.mode === 'chaos') {
    classifierStatus = 'skipped'
  } else if (state.stage === 'ml_processing') {
    classifierStatus = 'active'
    activeEdges.push('e-input-classifier')
  } else if (state.mlVerdict === 'MALICIOUS') {
    classifierStatus = 'blocked'
  } else if (state.mlVerdict === 'UNCERTAIN') {
    classifierStatus = 'flagged'
  }

  let moderationStatus: NodeStatus = 'idle'
  let moderationDatum: string | undefined
  if (state.mode === 'chaos') {
    moderationStatus = 'skipped'
  } else if (state.moderation && !state.moderation.safe) {
    moderationStatus = 'flagged'
    moderationDatum = state.moderation.categories.join(', ')
  } else if (state.mlVerdict || state.stage === 'final' || state.stage === 'complete') {
    moderationStatus = 'passed'
  }

  let routerStatus: NodeStatus = 'idle'
  if (state.mlVerdict || state.blocked || state.stage === 'final' || state.stage === 'complete') {
    routerStatus = state.blocked ? 'blocked' : state.dualAgentTriggered ? 'flagged' : 'passed'
    traversedEdges.push('e-classifier-router')
  }

  let adjudicationStatus: NodeStatus = 'skipped'
  if (state.dualAgentTriggered || state.stage === 'debate' || state.stage === 'dual_agent') {
    if (state.stage === 'debate' || state.stage === 'dual_agent') {
      adjudicationStatus = 'active'
      activeEdges.push('e-router-adjudication')
    } else if (state.blocked) {
      adjudicationStatus = 'blocked'
      traversedEdges.push('e-router-adjudication', 'e-adjudication-blocked')
    } else {
      adjudicationStatus = 'passed'
      traversedEdges.push('e-router-adjudication', 'e-adjudication-assistant')
    }
  }

  let assistantStatus: NodeStatus = 'idle'
  let blockedStatus: NodeStatus = 'idle'
  if (state.blocked) {
    blockedStatus = 'blocked'
    assistantStatus = 'skipped'
    if (!state.dualAgentTriggered) {
      traversedEdges.push('e-router-blocked')
    }
  } else if (state.stage === 'final' || state.stage === 'complete' || state.mlVerdict === 'SAFE') {
    assistantStatus = 'passed'
    if (!state.dualAgentTriggered) {
      traversedEdges.push('e-router-assistant')
    }
  }

  let toolsStatus: NodeStatus = 'idle'
  if (state.activeTools.length > 0) {
    toolsStatus = state.stage === 'complete' ? 'passed' : 'active'
    traversedEdges.push('e-assistant-tools')
  } else if (state.blocked) {
    toolsStatus = 'skipped'
  }

  return {
    nodes: [
      { id: 'input', status: 'passed', datum: state.query || undefined },
      {
        id: 'classifier',
        status: classifierStatus,
        datum: state.mlConfidence !== null ? `${(state.mlConfidence * 100).toFixed(0)}%` : undefined
      },
      { id: 'moderation', status: moderationStatus, datum: moderationDatum },
      { id: 'router', status: routerStatus, datum: state.mlVerdict || undefined },
      {
        id: 'adjudication',
        status: adjudicationStatus,
        datum: state.debate?.length ? `${state.debate.length} turns` : undefined
      },
      { id: 'assistant', status: assistantStatus, datum: state.toolPolicy },
      {
        id: 'tools',
        status: toolsStatus,
        datum: state.activeTools.length ? state.activeTools.join(', ') : undefined
      },
      { id: 'blocked', status: blockedStatus }
    ],
    activeEdges,
    traversedEdges
  }
}
