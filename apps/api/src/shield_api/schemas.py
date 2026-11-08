"""HTTP request/response models and the NDJSON chat event protocol.

These models are the public contract. Changing them changes
``contracts/shield-api.openapi.json``, which the web client is generated from.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from shield_engine import DecisionLayer, ToolPolicy, Verdict
from shield_engine.game import (
    AgentMode,
    AgentTier,
    AgentVerdict,
    HandleKind,
    MedalKind,
    NodeKind,
    OutcomeKind,
    RetiredNodeKind,
)

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
    # "blocked" is accepted only so the engine can explain its removal (spec 0020).
    kind: NodeKind | RetiredNodeKind
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
    expected_tool: str | None = None


class AgentToolSchema(BaseModel):
    name: str
    description: str
    allowed: bool


class AgentProfileSchema(BaseModel):
    objective: str
    tools: list[AgentToolSchema]
    token_budget: int


class GameLevelSchema(BaseModel):
    id: LevelId
    title: str
    difficulty: Literal["Easy", "Medium", "Hard"]
    summary: str
    protected_asset: str
    max_latency_ms: float
    max_cost_usd: float
    messages: list[LevelMessageSchema]
    # ``null`` on a classification-only level, where no model runs (spec 0021).
    agent: AgentProfileSchema | None
    agent_tier: AgentTier | None
    final_node_label: str


class GameCatalogResponse(BaseModel):
    levels: list[GameLevelSchema]
    checks: list[CheckDefinitionSchema]


PlayerTier = Literal["anonymous", "free", "paid"]


class PlayerRegisterRequest(BaseModel):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=6, max_length=512)]
    player_name: Annotated[str, Field(min_length=1, max_length=64)] | None = None


class PlayerLoginRequest(BaseModel):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=1, max_length=512)]


class PlayerRecoverRequest(BaseModel):
    email: Annotated[str, Field(min_length=3, max_length=254)]


class PlayerRecoverResponse(BaseModel):
    status: Literal["ok"] = "ok"


class PlayerSessionStatus(BaseModel):
    authenticated: bool
    is_anonymous: bool
    tier: PlayerTier
    email: str | None = None
    player_name: str
    ai_nodes_allowed: bool
    can_record_scores: bool
    daily_wave_limit: int | None = None
    wave_runs_used: int = 0
    daily_test_limit: int | None = None
    test_runs_used: int = 0


ProviderId = Literal["openai", "anthropic", "google", "groq", "deepseek", "qwen", "moonshot"]


class CustomAgentSchema(BaseModel):
    """The player's own agent (spec 0022). Limits are checked by the engine."""

    model_config = ConfigDict(extra="forbid")

    objective: Annotated[str, Field(max_length=1000)]
    tools: Annotated[list[AgentToolSchema], Field(max_length=10)] = Field(default_factory=list)


class CustomDatasetRowSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, Field(max_length=1000)]
    label: Literal["normal", "attack"]
    expected_tool: str | None = None


class ByokModelSchema(BaseModel):
    """Provider, model and key for one custom run. There is deliberately no URL field."""

    model_config = ConfigDict(extra="forbid")

    provider: ProviderId
    model: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:/-]+$")]
    # Length is checked in the router: a validation error here would echo the key.
    api_key: SecretStr


class CustomRunSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: CustomAgentSchema
    dataset: Annotated[list[CustomDatasetRowSchema], Field(max_length=50)]
    model: ByokModelSchema


RunLevelId = LevelId | Literal["custom"]


class NodePositionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class CustomSetupSchema(BaseModel):
    """A saved custom sandbox setup (spec 0023). Deliberately has no key field."""

    model_config = ConfigDict(extra="forbid")

    agent: CustomAgentSchema
    dataset: Annotated[list[CustomDatasetRowSchema], Field(max_length=50)] = Field(
        default_factory=list
    )
    provider: ProviderId = "openai"
    model: Annotated[str, Field(max_length=100, pattern=r"^[A-Za-z0-9._:/-]*$")] = ""


class SavedBoardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board: BoardGraphSchema
    positions: dict[str, NodePositionSchema] = Field(default_factory=dict)
    # Only for level "custom" (paid players).
    custom: CustomSetupSchema | None = None


class SavedBoardResponse(SavedBoardRequest):
    level_id: RunLevelId
    updated_at: datetime


class GameRunRequest(BaseModel):
    level_id: RunLevelId = "easy"
    board: BoardGraphSchema
    custom_message: str | None = None
    # Required when level_id is "custom" (paid players only, spec 0022).
    custom: CustomRunSchema | None = None


class HopTraceSchema(BaseModel):
    node_id: str
    handle: HandleKind
    latency_ms: float
    cost_usd: float
    detail: str


class AgentRunSchema(BaseModel):
    reply: str
    tool_calls: list[str]
    refused: bool
    verdict: AgentVerdict
    input_tokens: int
    output_tokens: int
    estimated_tokens: bool
    latency_ms: float
    cost_usd: float


class MessageTraceSchema(BaseModel):
    message_id: str
    text: str
    is_attack: bool
    outcome: OutcomeKind
    total_latency_ms: float
    total_cost_usd: float
    hops: list[HopTraceSchema]
    agent: AgentRunSchema | None = None


class WaveScoreSchema(BaseModel):
    total_score: int
    medal: MedalKind
    protection_points: int
    helpfulness_points: int
    tool_points: int
    token_points: int
    speed_points: int
    cost_points: int
    leak_penalty: int
    attacks_protected: int
    attacks_total: int
    attacks_leaked: int
    benign_helped: int
    benign_total: int
    false_alarms: int
    total_tokens: int
    avg_latency_ms: float
    total_cost_usd: float


class GameRunResponse(BaseModel):
    level_id: str
    traces: list[MessageTraceSchema]
    score: WaveScoreSchema
    agent_mode: AgentMode


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
    # Scoring scale the row was recorded under; the leaderboard lists only the current one.
    score_version: int = 2


class GameTrainRequest(BaseModel):
    algorithm: str = "logistic_regression"
    csv_text: str | None = None
    dataset: list[dict[str, Any]] | None = None


class GameTrainResponse(BaseModel):
    algorithm: str
    sample_count: int
    accuracy: float
    dataset: list[dict[str, Any]]
