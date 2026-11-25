import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Node } from '@vue-flow/core'
import { describe, expect, it, vi } from 'vitest'
import type { GameNodeData } from '../app/utils/gameBoard'
import {
  CAMPAIGN_TRAIN_MAX_BYTES,
  CUSTOM_TRAIN_MAX_BYTES,
  ML_TRAINING_NOTICE,
  REPLACE_MODEL_WARNING,
  applyTrainedModelToBoard,
  checkTrainingFile,
  decodeTrainingCsv,
  formatRemainingTrainings,
  needsReplaceConfirmation,
  triggerBeaconPurge
} from '../app/utils/mlTraining'

const APP_DIR = join(import.meta.dirname, '..', 'app')
const gameSource = () => readFileSync(join(APP_DIR, 'pages', 'game.vue'), 'utf-8')

const makeMlNode = (id: string, config: Record<string, unknown> = {}): Node<GameNodeData> => ({
  id,
  type: 'shield',
  position: { x: 0, y: 0 },
  data: {
    kind: 'ml_classifier',
    label: 'ML filter',
    subtitle: 'Trained classifier',
    handles: ['safe', 'suspicious'],
    latencyMs: 5,
    costUsd: 0,
    hasInput: true,
    isAnchor: false,
    status: 'idle',
    detail: 'Ready',
    hits: 0,
    arrivedCount: 0,
    flaggedCount: 0,
    traffic: { in: 0, pass: 0, block: 0 },
    tokens: 0,
    config
  }
})

describe('training upload hardening (spec 0045)', () => {
  it('[WEB-TRAIN-001] disables ML training controls for anonymous sessions and links to /auth/login', () => {
    const src = gameSource()
    expect(src).toContain('isAnonymous')
    expect(src).toContain('Sign in to train')
    expect(src).toContain('to="/auth/login"')
    expect(src).toMatch(/:disabled="isAnonymous/)
  })

  it('[WEB-TRAIN-002] checkTrainingFile rejects files over 131072 bytes (campaign) and 1310720 bytes (custom)', () => {
    expect(CAMPAIGN_TRAIN_MAX_BYTES).toBe(131_072)
    expect(CUSTOM_TRAIN_MAX_BYTES).toBe(1_310_720)
    expect(checkTrainingFile({ size: 131_072 }, 'campaign')).toEqual({ ok: true })
    expect(checkTrainingFile({ size: 131_073 }, 'campaign').ok).toBe(false)
    expect(checkTrainingFile({ size: 1_310_720 }, 'custom')).toEqual({ ok: true })
    expect(checkTrainingFile({ size: 1_310_721 }, 'custom').ok).toBe(false)
  })

  it('[WEB-TRAIN-003] decodeTrainingCsv rejects invalid UTF-8 and accepts valid UTF-8', () => {
    const invalid = new Uint8Array([0xff, 0xfe, 0xfd])
    expect(decodeTrainingCsv(invalid)).toEqual({
      ok: false,
      error: 'The file must be UTF-8 text.'
    })

    const valid = new TextEncoder().encode('text,label\nhello world,0\nattack prompt,1\n')
    expect(decodeTrainingCsv(valid)).toEqual({
      ok: true,
      text: 'text,label\nhello world,0\nattack prompt,1\n'
    })
  })

  it('[WEB-TRAIN-004] displays remaining daily trainings from session status', () => {
    expect(
      formatRemainingTrainings({ daily_train_limit: 3, train_runs_used: 1 })
    ).toBe('2 trainings left today')
    expect(
      formatRemainingTrainings({ daily_train_limit: 3, train_runs_used: 2 })
    ).toBe('1 training left today')
    expect(gameSource()).toContain('formatRemainingTrainings')
  })

  it('[WEB-TRAIN-005] displays the no-storage temporary model notice in the training panel', () => {
    expect(ML_TRAINING_NOTICE).toBe(
      'Your file is not stored. Only the trained model is kept, temporarily, and it is deleted when you leave the game, after 30 minutes idle, or when you retrain.'
    )
    expect(gameSource()).toContain('ML_TRAINING_NOTICE')
  })

  it('[WEB-TRAIN-006] stores model_id without dataset and marks other ML filter nodes retrain needed', () => {
    const nodes = [
      makeMlNode('ml_a', { algorithm: 'tfidf', dataset: [{ text: 'old', label: 0 }] }),
      makeMlNode('ml_b', { algorithm: 'tfidf', model_id: 'old-m' })
    ]
    const updated = applyTrainedModelToBoard(nodes, 'ml_a', 'm-new')
    const a = updated.find(n => n.id === 'ml_a')!
    const b = updated.find(n => n.id === 'ml_b')!
    expect(a.data?.config.model_id).toBe('m-new')
    expect('dataset' in (a.data?.config ?? {})).toBe(false)
    expect(a.data?.config.retrainNeeded).toBe(false)
    expect(b.data?.config.retrainNeeded).toBe(true)
    expect('model_id' in (b.data?.config ?? {})).toBe(false)
  })

  it('[WEB-TRAIN-007] marks ML filter Retrain needed on untrained_model_nodes or saved board load', () => {
    const src = gameSource()
    expect(src).toContain('untrained_model_nodes')
    expect(src).toContain('Retrain needed')
  })

  it('[WEB-TRAIN-008] purges models via DELETE /game/models on route leave and sendBeacon on pagehide', () => {
    const src = gameSource()
    expect(src).toContain('onBeforeRouteLeave')
    expect(src).toContain('purgeModels')
    expect(src).toContain('pagehide')
    expect(src).toContain('triggerBeaconPurge')

    const sendBeacon = vi.fn(() => true)
    triggerBeaconPurge({ sendBeacon } as unknown as Navigator)
    expect(sendBeacon).toHaveBeenCalledTimes(1)
    expect(sendBeacon.mock.calls[0]?.[0]).toBe('/api/v1/game/models/purge')
  })

  it('[WEB-TRAIN-009] warns before replacing another node trained model and allows re-training the same node', () => {
    const nodes = [
      makeMlNode('ml_a', { algorithm: 'tfidf', model_id: 'm1' }),
      makeMlNode('ml_b', { algorithm: 'tfidf' })
    ]
    expect(needsReplaceConfirmation(nodes, 'ml_b', 'm1')).toBe(true)
    expect(needsReplaceConfirmation(nodes, 'ml_a', 'm1')).toBe(false)
    expect(REPLACE_MODEL_WARNING).toBe(
      'Training this filter replaces your earlier trained model. The other ML filter will need a retrain.'
    )
    expect(gameSource()).toContain('REPLACE_MODEL_WARNING')
  })
})
