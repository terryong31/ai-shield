<script setup lang="ts">
import { ref, watch, type Ref } from 'vue'
import { VueFlow, type Edge, type Node } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import type { WorkflowState } from '~/types/workflow'

import UserNode from './UserNode.vue'
import MLNode from './MLNode.vue'
import SwitchNode from './SwitchNode.vue'
import DualAgentNode from './DualAgentNode.vue'
import AgentNode from './AgentNode.vue'
import OblivionNode from './OblivionNode.vue'
import ToolboxNode from './ToolboxNode.vue'

const props = defineProps<{
  workflowState: WorkflowState
}>()

// Cast back to Ref<Node[]>: Vue's deep ref unwrapping mangles Node's VNode-typed fields
const nodes = ref<Node[]>([
  {
    id: 'user',
    type: 'user',
    position: { x: 40, y: 140 },
    data: { label: 'Ready', status: 'idle' }
  },
  {
    id: 'ml',
    type: 'ml',
    position: { x: 260, y: 140 },
    data: { status: 'idle', confidence: null }
  },
  {
    id: 'switch',
    type: 'switch',
    position: { x: 480, y: 140 },
    data: { status: 'idle', verdict: '' }
  },
  {
    id: 'agent',
    type: 'agent',
    position: { x: 740, y: 30 },
    data: { status: 'idle', policy: '' }
  },
  {
    id: 'dualAgent',
    type: 'dualAgent',
    position: { x: 740, y: 180 },
    data: { status: 'idle', currentMessage: '' }
  },
  {
    id: 'oblivion',
    type: 'oblivion',
    position: { x: 740, y: 340 },
    data: { status: 'idle', reason: '' }
  },
  {
    id: 'toolbox',
    type: 'toolbox',
    position: { x: 1000, y: 100 },
    data: { status: 'idle', tools: [] }
  }
]) as Ref<Node[]>

const edges = ref<Edge[]>([
  { id: 'e-user-ml', source: 'user', target: 'ml', animated: false },
  { id: 'e-ml-switch', source: 'ml', target: 'switch', animated: false },
  { id: 'e-switch-agent', source: 'switch', sourceHandle: 'safe', target: 'agent', animated: false },
  { id: 'e-switch-dual', source: 'switch', sourceHandle: 'uncertain', target: 'dualAgent', animated: false },
  { id: 'e-switch-oblivion', source: 'switch', sourceHandle: 'danger', target: 'oblivion', animated: false },
  { id: 'e-dual-agent', source: 'dualAgent', sourceHandle: 'safe', target: 'agent', animated: false },
  { id: 'e-dual-oblivion', source: 'dualAgent', sourceHandle: 'danger', target: 'oblivion', animated: false },
  { id: 'e-agent-toolbox', source: 'agent', target: 'toolbox', animated: false }
]) as Ref<Edge[]>

type NodeStatus = 'idle' | 'active' | 'success' | 'warning' | 'error'

const verdictStatus = (verdict: WorkflowState['mlVerdict']): NodeStatus =>
  verdict === 'MALICIOUS' ? 'error' : verdict === 'SAFE' ? 'success' : 'warning'

watch(() => props.workflowState, (ws) => {
  const setData = (id: string, data: Record<string, unknown>) => {
    const node = nodes.value.find(n => n.id === id)
    if (node) node.data = data
  }

  setData('user', {
    label: ws.query ? ws.query.substring(0, 30) : 'Waiting...',
    status: ws.stage !== 'idle' ? 'success' : 'idle'
  })

  let mlStatus: NodeStatus = 'idle'
  if (ws.stage === 'ml_processing' && ws.mlConfidence === null) mlStatus = 'active'
  else if (ws.mlConfidence !== null) mlStatus = verdictStatus(ws.mlVerdict)
  setData('ml', { status: mlStatus, confidence: ws.mlConfidence })

  setData('switch', {
    status: ws.mlConfidence !== null ? verdictStatus(ws.mlVerdict) : 'idle',
    verdict: ws.mlVerdict
  })

  let dualStatus: NodeStatus = 'idle'
  if (ws.stage === 'debate') dualStatus = 'active'
  else if (ws.dualAgentTriggered) dualStatus = ws.blocked ? 'error' : 'success'
  setData('dualAgent', { status: dualStatus, currentMessage: ws.lastAgentMessage })

  setData('oblivion', {
    status: ws.blocked ? 'error' : 'idle',
    reason: ws.blocked ? 'Threat blocked by guardrails' : ''
  })

  setData('agent', {
    status: ws.stage === 'final' && !ws.blocked ? 'success' : 'idle',
    policy: ws.toolPolicy || ''
  })

  setData('toolbox', {
    status: ws.activeTools.length > 0 ? 'active' : 'idle',
    tools: ws.activeTools
  })

  const animated = new Set<string>()
  if (ws.stage === 'ml_processing') animated.add('e-user-ml')
  if (ws.stage === 'debate') ['e-switch-dual', 'e-dual-agent'].forEach(id => animated.add(id))
  if (ws.blocked) ['e-switch-oblivion', 'e-dual-oblivion'].forEach(id => animated.add(id))
  for (const edge of edges.value) edge.animated = animated.has(edge.id)
}, { deep: true })
</script>

<template>
  <div class="relative h-full w-full min-w-0 overflow-hidden bg-default">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :default-zoom="0.95"
      :min-zoom="0.4"
      :max-zoom="1.8"
      fit-view-on-init
      class="w-full h-full"
    >
      <template #node-user="nodeProps">
        <UserNode v-bind="nodeProps" />
      </template>
      <template #node-ml="nodeProps">
        <MLNode v-bind="nodeProps" />
      </template>
      <template #node-switch="nodeProps">
        <SwitchNode v-bind="nodeProps" />
      </template>
      <template #node-dualAgent="nodeProps">
        <DualAgentNode v-bind="nodeProps" />
      </template>
      <template #node-agent="nodeProps">
        <AgentNode v-bind="nodeProps" />
      </template>
      <template #node-oblivion="nodeProps">
        <OblivionNode v-bind="nodeProps" />
      </template>
      <template #node-toolbox="nodeProps">
        <ToolboxNode v-bind="nodeProps" />
      </template>

      <Background
        :gap="20"
        :size="1"
        color="var(--ui-border-accented)"
      />
      <Controls class="border-default" />
    </VueFlow>
  </div>
</template>
