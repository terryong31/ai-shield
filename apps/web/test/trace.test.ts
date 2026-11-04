import { describe, expect, it } from 'vitest'
import type { WorkflowState } from '../app/types/workflow'
import { applyChatEvent, shutdownNotice, type ChatTurn } from '../app/utils/chatStream'
import { derivePipelineGraph, statusAppearance, type NodeStatus } from '../app/utils/pipelineGraph'

const baseWorkflow = (): WorkflowState => ({
  query: 'hello',
  stage: 'start',
  mlConfidence: null,
  mlVerdict: '',
  lastAgentMessage: '',
  dualAgentTriggered: false,
  blocked: false,
  activeTools: [],
  mode: 'shield',
  moderation: null,
  debate: [],
  timeline: []
})

const makeTurn = (): ChatTurn => ({ workflow: baseWorkflow(), metadata: {}, text: '' })

describe('derivePipelineGraph and statusAppearance', () => {
  it('[WEB-TRACE-001] derives node statuses and active/traversed edges across workflow states', () => {
    const idleGraph = derivePipelineGraph(baseWorkflow())
    expect(idleGraph.nodes.find(n => n.id === 'input')?.status).toBe('idle')

    const mlRunning = derivePipelineGraph({ ...baseWorkflow(), stage: 'ml_processing' })
    expect(mlRunning.nodes.find(n => n.id === 'classifier')?.status).toBe('active')

    const safeDone = derivePipelineGraph({
      ...baseWorkflow(),
      stage: 'complete',
      mlVerdict: 'SAFE',
      mlConfidence: 0.1
    })
    expect(safeDone.nodes.find(n => n.id === 'assistant')?.status).toBe('passed')

    const debateRunning = derivePipelineGraph({
      ...baseWorkflow(),
      stage: 'dual_agent',
      mlVerdict: 'UNCERTAIN',
      dualAgentTriggered: true
    })
    expect(debateRunning.nodes.find(n => n.id === 'adjudication')?.status).toBe('active')

    const maliciousBlocked = derivePipelineGraph({
      ...baseWorkflow(),
      stage: 'complete',
      mlVerdict: 'MALICIOUS',
      blocked: true
    })
    expect(maliciousBlocked.nodes.find(n => n.id === 'blocked')?.status).toBe('blocked')
  })

  it('[WEB-TRACE-002] folds LLAMAGUARD_RESULT into moderation state and flags safety-check node', () => {
    const folded = applyChatEvent(makeTurn(), {
      type: 'LLAMAGUARD_RESULT',
      safe: false,
      categories: ['S1', 'S13']
    })
    expect(folded.workflow.moderation).toEqual({ safe: false, categories: ['S1', 'S13'] })

    const graph = derivePipelineGraph(folded.workflow)
    const modNode = graph.nodes.find(n => n.id === 'moderation')
    expect(modNode?.status).toBe('flagged')
    expect(modNode?.datum).toContain('S1')
  })

  it('[WEB-TRACE-003] keeps all DEBATE_TURN events in order without mutating previous state', () => {
    const t0 = makeTurn()
    const t1 = applyChatEvent(t0, { type: 'DEBATE_TURN', agent: 'ANALYST', message: 'Looks risky' })
    const t2 = applyChatEvent(t1, { type: 'DEBATE_TURN', agent: 'WARDEN', message: 'Restrict tools' })

    expect(t0.workflow.debate).toEqual([])
    expect(t2.workflow.debate).toEqual([
      { agent: 'ANALYST', message: 'Looks risky' },
      { agent: 'WARDEN', message: 'Restrict tools' }
    ])
  })

  it('[WEB-TRACE-004] records startedAt and timeline offsets when folded with timestamps', () => {
    const t0 = makeTurn()
    const t1 = applyChatEvent(t0, { type: 'START', query: 'test' }, 1000)
    const t2 = applyChatEvent(t1, { type: 'ML_RESULT', confidence: 0.2, verdict: 'SAFE' }, 1015)
    const t3 = applyChatEvent(t2, { type: 'FINAL_RESPONSE', text: 'ok' })

    expect(t1.startedAt).toBe(1000)
    expect(t3.workflow.timeline).toEqual([
      { type: 'START', at: 0, summary: 'Message received' },
      { type: 'ML_RESULT', at: 15, summary: 'SAFE (20.0%)' },
      { type: 'FINAL_RESPONSE', at: null, summary: 'Response ready' }
    ])
  })

  it('[WEB-TRACE-005] returns distinct non-empty icon and label for each node status', () => {
    const statuses: NodeStatus[] = ['idle', 'active', 'passed', 'flagged', 'blocked', 'skipped']
    const seen = new Set<string>()
    for (const st of statuses) {
      const app = statusAppearance(st)
      expect(app.icon.length).toBeGreaterThan(0)
      expect(app.label.length).toBeGreaterThan(0)
      const key = `${app.icon}:${app.label}`
      expect(seen.has(key)).toBe(false)
      seen.add(key)
    }
  })

  it('[WEB-TRACE-006] formats block notice using plain stage names', () => {
    expect(shutdownNotice('Bad input', 'LAYER_1_ML')).toBe('Blocked during screening. Bad input')
    expect(shutdownNotice('Policy denied', 'LAYER_2_DUAL_AGENT')).toBe('Blocked during agent review. Policy denied')
    expect(shutdownNotice('Rate limit', 'SYSTEM')).toBe('Blocked during system check. Rate limit')
  })

  it('[WEB-TRACE-007] keeps lastAgentMessage alongside debate list', () => {
    const folded = applyChatEvent(makeTurn(), {
      type: 'DEBATE_TURN',
      agent: 'WARDEN',
      message: 'Hold on'
    })
    expect(folded.workflow.lastAgentMessage).toBe('WARDEN: Hold on')
    expect(folded.workflow.debate).toEqual([{ agent: 'WARDEN', message: 'Hold on' }])
  })
})
