import { describe, expect, it } from 'vitest'
import type { ChatEvent } from '../app/types/api'
import type { WorkflowState } from '../app/types/workflow'
import { applyChatEvent, parseNdjson, shutdownNotice, splitNdjson, type ChatTurn } from '../app/utils/chatStream'

const idle: WorkflowState = {
  query: 'q',
  stage: 'start',
  mlConfidence: null,
  mlVerdict: '',
  lastAgentMessage: '',
  dualAgentTriggered: false,
  blocked: false,
  activeTools: [],
  mode: 'shield'
}

const turn = (): ChatTurn => ({ workflow: { ...idle }, metadata: {}, text: '' })

const fold = (...events: ChatEvent[]) => events.reduce(applyChatEvent, turn())

describe('splitNdjson', () => {
  it('[WEB-STREAM-001] returns complete lines and keeps the partial remainder', () => {
    const { lines, rest } = splitNdjson('{"a":1}\n{"b":2}\n{"c":')

    expect(lines).toEqual(['{"a":1}', '{"b":2}'])
    expect(rest).toBe('{"c":')
  })

  it('[WEB-STREAM-001] reassembles a line split across chunks', () => {
    const first = splitNdjson('{"type":"START","qu')
    const second = parseNdjson(first.rest + 'ery":"hi"}\n')

    expect(first.lines).toEqual([])
    expect(second.events).toEqual([{ type: 'START', query: 'hi' }])
  })

  it('[WEB-STREAM-002] produces no empty events for blank lines or \\n\\n separators', () => {
    const { lines } = splitNdjson('{"a":1}\n\n\n  \n{"b":2}\n\n')

    expect(lines).toEqual(['{"a":1}', '{"b":2}'])
  })
})

describe('parseNdjson', () => {
  it('[WEB-STREAM-005] reports malformed lines and keeps parsing', () => {
    const { events, errors } = parseNdjson('{"type":"START","query":"x"}\nnot json\n{"type":"FINAL_RESPONSE","text":"ok"}\n')

    expect(events.map(e => e.type)).toEqual(['START', 'FINAL_RESPONSE'])
    expect(errors).toEqual(['not json'])
  })
})

describe('applyChatEvent', () => {
  it('[WEB-STREAM-003] folds progress events into workflow state', () => {
    const state = fold(
      { type: 'STAGE_CHANGE', stage: 'ml_processing' },
      { type: 'ML_RESULT', confidence: 0.42, verdict: 'UNCERTAIN' },
      { type: 'DEBATE_TURN', agent: 'WARDEN', message: 'No dangerous tools.' },
      { type: 'POLICY_UPDATE', policy: 'RESTRICTED', allowed_tools: ['search_documents'] },
      { type: 'TOOL_START', tool: 'search_documents', args: {} }
    )

    expect(state.workflow).toMatchObject({
      stage: 'ml_processing',
      mlConfidence: 0.42,
      mlVerdict: 'UNCERTAIN',
      lastAgentMessage: 'WARDEN: No dangerous tools.',
      dualAgentTriggered: true,
      toolPolicy: 'RESTRICTED',
      activeTools: ['search_documents']
    })
    expect(state.metadata).toMatchObject({
      mlConfidence: 0.42,
      dualAgentTriggered: true,
      toolPolicy: 'RESTRICTED',
      allowedTools: ['search_documents']
    })
  })

  it('[WEB-STREAM-003] does not mutate the previous state', () => {
    const before = turn()

    applyChatEvent(before, { type: 'TOOL_START', tool: 't', args: {} })

    expect(before.workflow.activeTools).toEqual([])
  })

  it('[WEB-STREAM-004] marks blocks and shows the shutdown notice', () => {
    const state = fold({ type: 'BLOCK', reason: 'High confidence ML threat detection', layer: 'LAYER_1_ML' })

    expect(state.workflow.blocked).toBe(true)
    expect(state.metadata).toMatchObject({ blocked: true, reason: 'High confidence ML threat detection' })
    expect(state.text).toBe(shutdownNotice('High confidence ML threat detection'))
  })

  it('[WEB-STREAM-004] sets message text from final responses and errors', () => {
    expect(fold({ type: 'FINAL_RESPONSE', text: 'Hello' }).text).toBe('Hello')
    expect(fold({ type: 'ERROR', message: 'boom' }).text).toBe('Error: boom')
  })
})
