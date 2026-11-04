import type { WorkflowState } from '~/types/workflow'

const initialState = (mode: WorkflowState['mode'] = 'shield'): WorkflowState => ({
  query: '',
  stage: 'idle',
  mlConfidence: null,
  mlVerdict: '',
  lastAgentMessage: '',
  dualAgentTriggered: false,
  blocked: false,
  activeTools: [],
  mode
})

export const useShieldWorkflow = () => {
  const state = useState<WorkflowState>('shield_workflow_state', () => initialState())

  const resetState = () => {
    state.value = initialState(state.value.mode)
  }

  return { state, resetState }
}
