// Friendly aliases over the generated contract. Regenerate api.gen.ts with
// `mise run contract`; never edit it by hand.
import type { components } from './api.gen'

type Schemas = components['schemas']

export type AuditRecord = Schemas['AuditRecord']
export type ChatEvent = Schemas['ChatEvent']
export type ChatRequest = Schemas['ChatRequest']
export type ClearanceStatus = Schemas['ClearanceStatus']
export type DecisionLayer = Schemas['DecisionLayer']
export type FeedbackRequest = Schemas['FeedbackRequest']
export type FeedbackResponse = Schemas['FeedbackResponse']
export type Stats = Schemas['StatsResponse']
export type ToolPolicy = Schemas['ToolPolicy']
export type Verdict = Schemas['Verdict']
export type SecurityMode = NonNullable<ChatRequest['mode']>

export type BoardNodeSchema = Schemas['BoardNodeSchema']
export type BoardEdgeSchema = Schemas['BoardEdgeSchema']
export type BoardGraphSchema = Schemas['BoardGraphSchema']
export type ByodConfigSchema = Schemas['ByodConfigSchema']
export type CheckDefinitionSchema = Schemas['CheckDefinitionSchema']
export type GameCatalogResponse = Schemas['GameCatalogResponse']
export type GameLevelSchema = Schemas['GameLevelSchema']
export type GameRunRequest = Schemas['GameRunRequest']
export type GameRunResponse = Schemas['GameRunResponse']
export type GameTrainRequest = Schemas['GameTrainRequest']
export type GameTrainResponse = Schemas['GameTrainResponse']
export type HopTraceSchema = Schemas['HopTraceSchema']
export type MessageTraceSchema = Schemas['MessageTraceSchema']
export type ScoreCreateRequest = Schemas['ScoreCreateRequest']
export type ScoreRecord = Schemas['ScoreRecord']
export type WaveScoreSchema = Schemas['WaveScoreSchema']
export type LevelId = GameLevelSchema['id']
export type NodeKind = BoardNodeSchema['kind']
export type HandleKind = BoardEdgeSchema['source_handle']
export type MedalKind = WaveScoreSchema['medal']
