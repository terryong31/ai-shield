"""HTTP request/response models for the game gateway.

These models are the public contract. Changing them changes
``contracts/shield-api.openapi.json``, which the web client is generated from.
"""

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictInt,
    StrictStr,
    StringConstraints,
    model_validator,
)

from shield_engine.game import (
    AgentMode,
    AgentTier,
    AgentVerdict,
    DifficultyCategory,
    HandleKind,
    LevelId,
    LevelTier,
    MedalKind,
    NodeKind,
    OutcomeKind,
    RetiredNodeKind,
)


class HealthResponse(BaseModel):
    status: Literal["healthy"]
    service: str
    version: str
    model_loaded: bool
    # Agent tiers that run a live model; the rest use the offline stand-in.
    agent_tiers: list[AgentTier]
    storage_backend: Literal["supabase", "memory"]


class ClearanceRequest(BaseModel):
    """An admin's Supabase Auth credentials, checked once and never stored."""

    email: Annotated[str, Field(min_length=3, max_length=320)]
    password: Annotated[str, Field(min_length=1, max_length=512)]


class ClearanceStatus(BaseModel):
    granted: bool
    expires_at: datetime | None


# --- Game models --------------------------------------------------------------


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
    forbidden_tools: list[str] = Field(default_factory=list)


class AgentToolSchema(BaseModel):
    name: str
    description: str
    allowed: bool
    dual_use: bool = False


class AgentProfileSchema(BaseModel):
    objective: str
    tools: list[AgentToolSchema]
    token_budget: int


class LevelConstraintsSchema(BaseModel):
    max_check_nodes: int | None = None
    disabled_checks: list[NodeKind] = Field(default_factory=list)
    max_avg_latency_ms: float | None = None
    max_total_cost_usd: float | None = None
    max_tokens: int | None = None


class FollowUpChallengeSchema(BaseModel):
    description: str
    max_check_nodes: int | None = None
    forbidden_checks: list[NodeKind] = Field(default_factory=list)
    max_avg_latency_ms: float | None = None
    max_total_cost_usd: float | None = None
    max_tokens: int | None = None


class GameLevelSchema(BaseModel):
    id: LevelId
    order: int
    tier: LevelTier
    title: str
    difficulty: DifficultyCategory
    summary: str
    protected_asset: str
    max_latency_ms: float
    max_cost_usd: float
    messages: list[LevelMessageSchema]
    # ``null`` on a classification-only level, where no model runs (spec 0021).
    agent: AgentProfileSchema | None
    tags: list[str] = Field(default_factory=list)
    constraints: LevelConstraintsSchema = Field(default_factory=LevelConstraintsSchema)
    follow_up: FollowUpChallengeSchema | None = None
    agent_tier: AgentTier | None
    final_node_label: str


class GameCatalogResponse(BaseModel):
    levels: list[GameLevelSchema]
    checks: list[CheckDefinitionSchema]
    jev_key_configured: bool = False
    ai_key_configured: bool = False
    self_upgrade_enabled: bool = False


PlayerTier = Literal["anonymous", "free", "paid"]


# A light shape check so obvious typos are rejected before Supabase is called (spec 0027).
PlayerEmail = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]


def _validate_strong_password(value: str) -> str:
    if (
        len(value) < 8
        or not re.search(r"\d", value)
        or not re.search(r"[a-z]", value)
        or not re.search(r"[A-Z]", value)
    ):
        raise ValueError(
            "Password must be at least 8 characters and include a number, "
            "a lowercase letter, and an uppercase letter."
        )
    return value


StrongPassword = Annotated[
    str,
    Field(min_length=8, max_length=512),
    AfterValidator(_validate_strong_password),
]


class PlayerRegisterRequest(BaseModel):
    email: PlayerEmail
    password: StrongPassword
    player_name: Annotated[str, Field(min_length=1, max_length=64)] | None = None


class PlayerLoginRequest(BaseModel):
    email: PlayerEmail
    password: Annotated[str, Field(min_length=8, max_length=512)]


class PlayerResendRequest(BaseModel):
    email: PlayerEmail


CurrentPassword = Annotated[str, Field(min_length=1, max_length=512)]
NewPassword = StrongPassword


class AccountPasswordRequest(BaseModel):
    """Change password (spec 0025). The current password is checked first."""

    model_config = ConfigDict(extra="forbid")

    current_password: CurrentPassword
    new_password: NewPassword

    @model_validator(mode="after")
    def _new_differs(self) -> "AccountPasswordRequest":
        if self.new_password == self.current_password:
            raise ValueError("The new password must differ from the current one.")
        return self


class AccountEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_email: PlayerEmail
    current_password: CurrentPassword


class AccountResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: CurrentPassword


class AccountDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: CurrentPassword
    confirm: Literal["DELETE"]


class AccountResetResponse(BaseModel):
    scores_removed: int
    boards_removed: int


class PlayerConfirmationResponse(BaseModel):
    """Sent for every register or resend that needs email confirmation, whatever the email."""

    status: Literal["confirmation_sent"] = "confirmation_sent"


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
    daily_train_limit: int | None = 0
    train_runs_used: int = 0


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
    level_id: RunLevelId = "easy-1"
    board: BoardGraphSchema
    custom_message: Annotated[str, Field(max_length=1000)] | None = None
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
    won: bool = False
    constraint_violations: list[str] = Field(default_factory=list)
    follow_up_passed: bool = False
    follow_up_feedback: str = ""


class GameRunResponse(BaseModel):
    level_id: str
    traces: list[MessageTraceSchema]
    score: WaveScoreSchema
    agent_mode: AgentMode
    untrained_model_nodes: list[str] = Field(default_factory=list)


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
    won: bool = False
    mastered: bool = False


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
    score_version: int = 3
    won: bool = False
    mastered: bool = False


class DifficultyLeaderboardEntry(BaseModel):
    player_name: str
    difficulty: DifficultyCategory | Literal["All"]
    total_score: int
    max_possible_score: int
    levels_solved: int
    levels_mastered: int
    levels_total: int
    avg_latency_ms: float
    total_cost_usd: float


class LeaderboardRankResponse(BaseModel):
    difficulty: DifficultyCategory
    rank: int | None
    total_score: int | None


class LevelProgressItem(BaseModel):
    level_id: LevelId
    difficulty: DifficultyCategory
    best_score: int
    medal: MedalKind
    won: bool
    mastered: bool


class DifficultyProgressSummary(BaseModel):
    difficulty: DifficultyCategory
    total_score: int
    max_possible_score: int
    levels_solved: int
    levels_mastered: int
    levels_total: int


class PlayerProgressResponse(BaseModel):
    levels: list[LevelProgressItem]
    difficulties: list[DifficultyProgressSummary]


class TrainingRowSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: StrictStr
    label: StrictInt | StrictStr


class GameTrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: str = "logistic_regression"
    csv_text: StrictStr | None = None
    dataset: list[TrainingRowSchema] | None = None
    level_id: RunLevelId | None = None


class GameTrainResponse(BaseModel):
    model_id: str
    algorithm: str
    sample_count: int
    accuracy: float
    expires_at: datetime
