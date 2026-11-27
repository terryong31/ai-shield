"""The game board, its checks, levels and scoring (spec 0016).

This package only re-exports. The code lives in the submodules `types`, `detectors`,
`validation`, `runner`, `scoring`, `levels`, `agent`, `custom` and `model_signing`
(spec 0055). Import from here; the submodules may change.
"""

# The lists are packed by hand to keep this facade short.
# fmt: off
# isort: off
from .agent import (
    AGENT_RULE_LIMIT, AGENT_RULE_MAX_CHARS, AgentMode, AgentProfile, AgentRun, AgentTier,
    AgentTool, AgentUnavailableError, AgentVerdict, build_agent_graph, simulate_agent,
)
from .custom import (
    build_custom_messages, parse_custom_dataset, run_custom_message, run_custom_wave,
    validate_custom_profile,
)
from .detectors import (
    TextCleaner, WordFilterDetector, fit_classifier, parse_dataset_csv, strip_training_data,
    train_custom_classifier, validate_training_rows,
)
from .levels import (
    ALL_LEVEL_IDS, BriefingExample, DifficultyCategory, FollowUpChallenge, GameLevel,
    LEVEL_IDS_BY_DIFFICULTY, LevelConstraints, LevelId, LevelMessage, LevelTier, NodeKind,
    RETIRED_LEVEL_IDS, get_level, get_levels,
)
from .model_signing import (
    ModelSignatureError, load_signed_model, sign_model,
)
from .runner import (
    evaluate_message, run_single_message, run_wave,
)
from .scoring import (
    agent_mode_for, fair_score, model_for_level, score_campaign, score_traces, score_wave,
)
from .types import (
    ALLOWED_ML_ALGORITHMS, BoardEdge, BoardGraph, BoardNode, BoardValidationError,
    CheckDefinition, CleanedText, FairScore, FittedClassifier, HandleKind, HopTrace,
    MLAlgorithmKind, MedalKind, MessageTrace, OutcomeKind, PathStep, RETIRED_BLOCKED_MESSAGE,
    RetiredNodeKind, RunStop, TrainingSummary, WaveResult, WaveScore, WordFilterResult,
    get_check_catalog,
)
from .validation import (
    validate_board, validate_board_for_level,
)
# isort: on

__all__ = [
    "AGENT_RULE_LIMIT", "AGENT_RULE_MAX_CHARS", "ALLOWED_ML_ALGORITHMS", "ALL_LEVEL_IDS",
    "LEVEL_IDS_BY_DIFFICULTY", "RETIRED_BLOCKED_MESSAGE", "RETIRED_LEVEL_IDS", "AgentMode",
    "AgentProfile", "AgentRun", "AgentTier", "AgentTool", "AgentUnavailableError",
    "AgentVerdict", "BoardEdge", "BoardGraph", "BoardNode", "BoardValidationError",
    "BriefingExample", "CheckDefinition", "CleanedText", "DifficultyCategory", "FairScore",
    "FittedClassifier", "FollowUpChallenge", "GameLevel", "HandleKind", "HopTrace",
    "LevelConstraints", "LevelId", "LevelMessage", "LevelTier", "MLAlgorithmKind", "MedalKind",
    "MessageTrace", "ModelSignatureError", "NodeKind", "OutcomeKind", "PathStep",
    "RetiredNodeKind", "RunStop", "TextCleaner", "TrainingSummary", "WaveResult", "WaveScore",
    "WordFilterDetector", "WordFilterResult", "agent_mode_for", "build_agent_graph",
    "build_custom_messages", "evaluate_message", "fair_score", "fit_classifier",
    "get_check_catalog", "get_level", "get_levels", "load_signed_model", "model_for_level",
    "parse_custom_dataset", "parse_dataset_csv", "run_custom_message", "run_custom_wave",
    "run_single_message", "run_wave", "score_campaign", "score_traces", "score_wave",
    "sign_model", "simulate_agent", "strip_training_data", "train_custom_classifier",
    "validate_board", "validate_board_for_level", "validate_custom_profile",
    "validate_training_rows",
]
# fmt: on
