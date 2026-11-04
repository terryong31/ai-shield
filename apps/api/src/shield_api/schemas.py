"""HTTP request/response models and the NDJSON chat event protocol.

These models are the public contract. Changing them changes
``contracts/shield-api.openapi.json``, which the web client is generated from.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from shield_engine import DecisionLayer, ToolPolicy, Verdict
from shield_engine.game import HandleKind, MedalKind, NodeKind, OutcomeKind

Mode = Literal["shield", "guardrail", "chaos"]
Prompt = Annotated[str, Field(min_length=1, max_length=8000)]


class HealthResponse(BaseModel):
    status: Literal["healthy"]
    service: str
    version: str
    model_loaded: bool
    moderation_enabled: bool
    adjudication_enabled: bool
    audit_backend: Literal["sqlite", "supabase", "memory"]


class PredictRequest(BaseModel):
    message: Prompt


class PredictResponse(BaseModel):
    verdict: Verdict
    confidence_score: float
    is_malicious: bool
    override: bool


class ScreenRequest(BaseModel):
    message: Prompt
    mode: Mode = "shield"


class ScreenResponse(BaseModel):
    verdict: Verdict
    policy: ToolPolicy
    blocked: bool
    layer: DecisionLayer
    reason: str
    ml_confidence: float
    adjudicated: bool


class ChatRequest(BaseModel):
    message: Prompt
    mode: Mode = "shield"


class ClearanceRequest(BaseModel):
    passphrase: Annotated[str, Field(min_length=1, max_length=512)]
    email: str | None = None


class ClearanceStatus(BaseModel):
    granted: bool
    expires_at: datetime | None


class FeedbackRequest(BaseModel):
    prompt: Prompt
    human_label: Literal[0, 1]
    request_id: str | None = None


class FeedbackResponse(BaseModel):
    status: Literal["success"]


class AuditRecord(BaseModel):
    id: str
    created_at: datetime
    query: str
    action: Literal["ALLOWED", "BLOCKED"]
    reason: str
    layer: str
    reviewed: bool = False
    human_label: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StatsResponse(BaseModel):
    total: int
    blocked: int
    allowed: int
    block_rate: float


# --- Chat stream events (one JSON object per NDJSON line) -------------------


class StartEvent(BaseModel):
    type: Literal["START"] = "START"
    query: str


class StageChangeEvent(BaseModel):
    type: Literal["STAGE_CHANGE"] = "STAGE_CHANGE"
    stage: Literal["ml_processing", "debate", "final"]


class MlResultEvent(BaseModel):
    type: Literal["ML_RESULT"] = "ML_RESULT"
    confidence: float
    verdict: Verdict


class ModerationEvent(BaseModel):
    type: Literal["LLAMAGUARD_RESULT"] = "LLAMAGUARD_RESULT"
    safe: bool
    categories: list[str]


class DebateTurnEvent(BaseModel):
    type: Literal["DEBATE_TURN"] = "DEBATE_TURN"
    agent: Literal["ANALYST", "WARDEN"]
    message: str


class BlockEvent(BaseModel):
    type: Literal["BLOCK"] = "BLOCK"
    reason: str
    layer: DecisionLayer


class PolicyUpdateEvent(BaseModel):
    type: Literal["POLICY_UPDATE"] = "POLICY_UPDATE"
    policy: ToolPolicy
    allowed_tools: list[str]


class ToolStartEvent(BaseModel):
    type: Literal["TOOL_START"] = "TOOL_START"
    tool: str
    args: dict[str, Any]


class ToolEndEvent(BaseModel):
    type: Literal["TOOL_END"] = "TOOL_END"
    tool: str
    result: Any


class FinalResponseEvent(BaseModel):
    type: Literal["FINAL_RESPONSE"] = "FINAL_RESPONSE"
    text: str


class ErrorEvent(BaseModel):
    type: Literal["ERROR"] = "ERROR"
    message: str


ChatEvent = Annotated[
    StartEvent
    | StageChangeEvent
    | MlResultEvent
    | ModerationEvent
    | DebateTurnEvent
    | BlockEvent
    | PolicyUpdateEvent
    | ToolStartEvent
    | ToolEndEvent
    | FinalResponseEvent
    | ErrorEvent,
    Field(discriminator="type"),
]


# --- Game models --------------------------------------------------------------

LevelId = Literal["easy", "medium", "hard"]


class BoardNodeSchema(BaseModel):
    id: str
    kind: NodeKind
    config: dict[str, Any] = Field(default_factory=dict)


class BoardEdgeSchema(BaseModel):
    id: str
    source: str
    source_handle: HandleKind
    target: str


class BoardGraphSchema(BaseModel):
    nodes: list[BoardNodeSchema]
    edges: list[BoardEdgeSchema]


class CheckDefinitionSchema(BaseModel):
    kind: NodeKind
    label: str
    summary: str
    handles: list[HandleKind]
    latency_ms: float
    cost_usd: float


class LevelMessageSchema(BaseModel):
    id: str
    text: str
    is_attack: bool
    category: str


class GameLevelSchema(BaseModel):
    id: LevelId
    title: str
    difficulty: Literal["Easy", "Medium", "Hard"]
    summary: str
    protected_asset: str
    max_latency_ms: float
    max_cost_usd: float
    messages: list[LevelMessageSchema]


class GameCatalogResponse(BaseModel):
    levels: list[GameLevelSchema]
    checks: list[CheckDefinitionSchema]


class ByodConfigSchema(BaseModel):
    provider: Literal["offline", "openai", "groq"] = "offline"
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None


class GameRunRequest(BaseModel):
    level_id: LevelId = "easy"
    board: BoardGraphSchema
    custom_message: str | None = None
    byod: ByodConfigSchema | None = None


class HopTraceSchema(BaseModel):
    node_id: str
    handle: HandleKind
    latency_ms: float
    cost_usd: float
    detail: str


class MessageTraceSchema(BaseModel):
    message_id: str
    text: str
    is_attack: bool
    outcome: OutcomeKind
    total_latency_ms: float
    total_cost_usd: float
    hops: list[HopTraceSchema]


class WaveScoreSchema(BaseModel):
    total_score: int
    medal: MedalKind
    protection_points: int
    accuracy_points: int
    speed_points: int
    cost_points: int
    attacks_blocked: int
    attacks_total: int
    attacks_leaked: int
    benign_passed: int
    benign_total: int
    false_alarms: int
    avg_latency_ms: float
    total_cost_usd: float


class GameRunResponse(BaseModel):
    level_id: str
    traces: list[MessageTraceSchema]
    score: WaveScoreSchema


class ScoreCreateRequest(BaseModel):
    player_name: Annotated[str, Field(min_length=1, max_length=64)]
    level_id: LevelId
    total_score: int
    medal: MedalKind
    attacks_blocked: int
    attacks_total: int
    false_alarms: int
    avg_latency_ms: float
    total_cost_usd: float
    board: BoardGraphSchema


class ScoreRecord(BaseModel):
    id: str
    created_at: datetime
    player_name: str
    level_id: LevelId
    total_score: int
    medal: MedalKind
    attacks_blocked: int
    attacks_total: int
    false_alarms: int
    avg_latency_ms: float
    total_cost_usd: float
    board: BoardGraphSchema


class GameTrainRequest(BaseModel):
    algorithm: str = "logistic_regression"
    csv_text: str | None = None
    dataset: list[dict[str, Any]] | None = None


class GameTrainResponse(BaseModel):
    algorithm: str
    sample_count: int
    accuracy: float
    dataset: list[dict[str, Any]]
