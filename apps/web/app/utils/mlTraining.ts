import type { Node } from '@vue-flow/core'
import type { GameNodeData } from '~/utils/gameBoard'

export const CAMPAIGN_TRAIN_MAX_BYTES = 131_072
export const CUSTOM_TRAIN_MAX_BYTES = 1_310_720

export const ML_TRAINING_NOTICE = 'Your file is not stored. Only the trained model is kept, temporarily, and it is deleted when you leave the game, after 30 minutes idle, or when you retrain.'

export const REPLACE_MODEL_WARNING = 'Training this filter replaces your earlier trained model. The other ML filter will need a retrain.'

export function checkTrainingFile(
  file: { size: number },
  mode: 'campaign' | 'custom'
): { ok: true } | { ok: false, error: string } {
  const maxBytes = mode === 'custom' ? CUSTOM_TRAIN_MAX_BYTES : CAMPAIGN_TRAIN_MAX_BYTES
  if (file.size > maxBytes) {
    const label = mode === 'custom' ? '1.25 MB' : '128 KB'
    return { ok: false, error: `File exceeds the ${label} limit.` }
  }
  return { ok: true }
}

export function decodeTrainingCsv(
  bytes: Uint8Array | ArrayBuffer
): { ok: true, text: string } | { ok: false, error: string } {
  try {
    const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)
    const decoder = new TextDecoder('utf-8', { fatal: true })
    return { ok: true, text: decoder.decode(view) }
  } catch {
    return { ok: false, error: 'The file must be UTF-8 text.' }
  }
}

export function formatRemainingTrainings(
  session: { daily_train_limit?: number | null, train_runs_used?: number | null } | null | undefined
): string {
  const limit = session?.daily_train_limit ?? 0
  const used = session?.train_runs_used ?? 0
  const remaining = Math.max(0, limit - used)
  return `${remaining} ${remaining === 1 ? 'training' : 'trainings'} left today`
}

export function needsReplaceConfirmation(
  nodes: Node<GameNodeData>[],
  targetNodeId: string,
  activeModelId: string | null
): boolean {
  if (!activeModelId) return false
  return nodes.some(
    n =>
      n.id !== targetNodeId
      && n.data?.kind === 'ml_classifier'
      && n.data?.config.model_id === activeModelId
  )
}

export function applyTrainedModelToBoard(
  nodes: Node<GameNodeData>[],
  trainedNodeId: string,
  modelId: string
): Node<GameNodeData>[] {
  return nodes.map((node) => {
    if (node.data?.kind !== 'ml_classifier') return node
    const nextConfig: Record<string, unknown> = { ...node.data.config }
    delete nextConfig.dataset
    if (node.id === trainedNodeId) {
      nextConfig.model_id = modelId
      nextConfig.retrainNeeded = false
    } else {
      delete nextConfig.model_id
      nextConfig.retrainNeeded = true
    }
    return {
      ...node,
      data: {
        ...node.data,
        config: nextConfig
      }
    }
  })
}

export function markUntrainedModelNodes(
  nodes: Node<GameNodeData>[],
  untrainedIds: readonly string[],
  options?: { allMl?: boolean }
): Node<GameNodeData>[] {
  const targetSet = new Set(untrainedIds)
  return nodes.map((node) => {
    if (node.data?.kind !== 'ml_classifier') return node
    if (!options?.allMl && !targetSet.has(node.id)) return node
    const nextConfig: Record<string, unknown> = { ...node.data.config, retrainNeeded: true }
    delete nextConfig.model_id
    delete nextConfig.dataset
    return {
      ...node,
      data: {
        ...node.data,
        config: nextConfig
      }
    }
  })
}

export function triggerBeaconPurge(nav: Navigator | undefined): void {
  if (!nav || typeof nav.sendBeacon !== 'function') return
  nav.sendBeacon('/api/v1/game/models/purge')
}
