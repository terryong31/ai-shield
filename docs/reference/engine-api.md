# Engine API reference

Public Python API of `shield-engine` (import name `shield_engine`), version 0.1.0:
the checks behind the prompt-injection defence game.
Source: [`packages/engine/src/shield_engine`](../../packages/engine/src/shield_engine).

All value types are frozen dataclasses with `slots=True`. All enums are `StrEnum`,
so `str(Verdict.SAFE) == "SAFE"`. Spec 0026 removed the original screening
pipeline (`Shield`, moderation, debate, tool policy, events, feedback and the
evaluation runner); the game was the only remaining user.

- [Top-level exports](#top-level-exports-shield_engine__all__)
- [Value types](#value-types)
- [Ports](#ports)
- [`ClassifierDetector`](#classifierdetector)
- [`shield_engine.untrusted`](#shield_engineuntrusted)
- [`shield_engine.models`](#shield_enginemodels)
- [`shield_engine.training`](#shield_enginetraining)
- [`shield_engine.dataset`](#shield_enginedataset)
- [`shield_engine.testing`](#shield_enginetesting)
- [`shield_engine.adapters.groq`](#shield_engineadaptersgroq)
- [`shield_engine.game`](#shield_enginegame)

## Top-level exports (`shield_engine.__all__`)

`ChatCompletion`, `ChatMessage`, `ChatModel`, `ClassifierDetector`, `Signal`,
`UsageChatModel`, `Verdict`, `__version__`, `wrap_untrusted`. Game types and
functions live in `shield_engine.game`.

## Value types

`Verdict`: `SAFE`, `UNCERTAIN`, `MALICIOUS`.

`Signal`: one detector's opinion about a prompt.

| Field | Type | Meaning |
| --- | --- | --- |
| `detector` | `str` | Detector name (`"classifier"`) |
| `verdict` | `Verdict` | |
| `score` | `float` | P(malicious) |
| `override` | `bool` = `False` | Reserved; always `False` since the feedback store was removed |
| `details` | `Mapping[str, Any]` = `{}` | For example `sensitive_floor_applied` |

## Ports

Structural `typing.Protocol`s in `shield_engine.ports`. Any object with matching
methods satisfies them.

| Name | Shape |
| --- | --- |
| `ChatMessage` | dataclass `(role: Literal["system", "user", "assistant"], content: str)` |
| `ChatCompletion` | dataclass `(text: str, input_tokens: int \| None = None, output_tokens: int \| None = None)` |
| `ChatModel` | `async complete(messages, *, temperature=0.0, max_tokens=None) -> str` |
| `UsageChatModel` | `async complete_with_usage(messages, *, temperature=0.0, max_tokens=None, thinking=False) -> ChatCompletion`; runs the game's AI Agent (spec 0020, always `thinking=False`) and LLM checks (`thinking` from the node's `config.thinking`, ENG-CHECK-007). Providers without a reasoning control ignore `thinking` |
| `Classifier` | `score(text: str) -> Signal` (synchronous) |

## `ClassifierDetector`

The baseline behind the game's `ML filter` (`ml_classifier`) node when `algorithm="tfidf"` is used without a custom dataset.

```python
ClassifierDetector(
    vectorizer: Vectorizer,            # has transform(texts: list[str]) -> Any
    model: ProbabilisticModel,         # has predict_proba(features) -> Any
    *,
    malicious_threshold: float = 0.85,
    safe_threshold: float = 0.15,
    sensitive_keywords: Sequence[str] = SENSITIVE_KEYWORDS,
    sensitive_ceiling: float = 0.35,
    sensitive_floor: float = 0.40,
)
```

Raises `ValueError` unless `0 <= safe_threshold < malicious_threshold <= 1`.
`score(text) -> Signal`: `p = predict_proba(transform([text]))[0][1]`; if
`p < sensitive_ceiling` and the lower-cased text contains a sensitive keyword,
`p = sensitive_floor`; then `p >= malicious_threshold` is MALICIOUS,
`p <= safe_threshold` SAFE, otherwise UNCERTAIN.

`SENSITIVE_KEYWORDS`: `sales`, `revenue`, `employee`, `salary`, `database`, `sql`,
`delete`, `personal`, `customer`, `member`, `boss`, `org`, `chart`, `hierarchy`,
`email`, `private`, `confidential`, `internal`, `table`, `drop`.

## `shield_engine.untrusted`

`wrap_untrusted(prompt: str) -> str` returns
`"<untrusted_prompt>\n{prompt}\n</untrusted_prompt>"`, replacing any
`<untrusted_prompt>` or `</untrusted_prompt>` look-alike inside the prompt
(case- and whitespace-insensitive) with `[delimiter removed]`. Every prompt the
game sends to an LLM goes through it.

## `shield_engine.models`

| Symbol | Description |
| --- | --- |
| `BASELINE_DIR` | `Path` of the bundled `models/baseline/` directory |
| `MODEL_FILE`, `VECTORIZER_FILE`, `METADATA_FILE` | `"model.joblib"`, `"vectorizer.joblib"`, `"metadata.json"` |
| `ArtifactIntegrityError` | `RuntimeError` subclass: artifact or metadata missing, or digest mismatch |
| `sha256_file(path: Path) -> str` | Hex SHA-256 of a file |
| `read_metadata(directory: Path = BASELINE_DIR) -> dict` | Parses `metadata.json`; raises `ArtifactIntegrityError` if missing |
| `verify_artifacts(directory: Path = BASELINE_DIR) -> dict` | Checks every entry of `metadata["files"]` against its SHA-256; returns the metadata or raises `ArtifactIntegrityError` |
| `load_baseline(*, directory: Path = BASELINE_DIR, **kwargs) -> ClassifierDetector` | Verifies, then `joblib.load`s vectorizer and model; `kwargs` go to `ClassifierDetector` (thresholds, keywords) |

`metadata.json` fields: `name`, `algorithm`, `sklearn_version`, `trained_at`,
`hyperparameters` (`replicate`, `random_state`), `training_data` (`examples`,
`path`, `sha256`), `files` (file name to SHA-256).

## `shield_engine.training`

```python
train_baseline(
    examples: list[Example],
    out_dir: Path,
    *,
    dataset_path: Path | None = None,
    replicate: int = 20,
    random_state: int = 42,
) -> dict[str, Any]
```

Fits `TfidfVectorizer(max_features=5000)` and
`SGDClassifier(loss="log_loss", max_iter=1000, random_state=random_state)` on the
examples repeated `replicate` times, writes `model.joblib`, `vectorizer.joblib` and
`metadata.json` to `out_dir` (created if missing), and returns the metadata.
`training_data.path`/`sha256` are `None` when `dataset_path` is not given.

## `shield_engine.dataset`

| Symbol | Signature / fields |
| --- | --- |
| `Example` | dataclass `Example(text: str, label: int, source: str \| None = None, category: str \| None = None)`; label 1 = malicious |
| `DatasetError` | `ValueError` subclass; message names the file and 1-based line |
| `load_jsonl(path: Path) -> list[Example]` | Skips blank lines. Raises `DatasetError` on invalid JSON, a non-object row, non-string `text`, or `label` not exactly `0` or `1` (booleans rejected) |

The `shield-engine train --data <jsonl> [--out DIR] [--seed N]` command (`mise run train`)
loads a dataset with `load_jsonl` and calls `train_baseline`.

## `shield_engine.testing`

Deterministic doubles, shipped in the package for host tests. All are mutable
dataclasses that record their calls.

| Class | Fields (default) | Behaviour |
| --- | --- | --- |
| `StaticClassifier` | `verdict=SAFE`, `probability=0.05`, `calls=[]` | `score()` returns `Signal("classifier", verdict, probability)` |
| `ScriptedChatModel` | `replies: list[str \| BaseException]` (required), `calls=[]` | Pops replies in order; raises a queued exception; raises `AssertionError` when empty |
| `ScriptedUsageChatModel` | `replies: list[ChatCompletion \| str \| BaseException]` (required), `default=None`, `calls=[]` | `UsageChatModel` double: pops queued replies, then returns `default`; a queued `str` has no token usage; raises a queued exception; raises `AssertionError` when empty and no `default` |

## `shield_engine.adapters.groq`

Requires the `groq` extra (`shield-engine[groq]`); importing the module without it
raises `ImportError`.

```python
GroqChatModel(api_key: str, model: str, *, timeout: float = 30.0)
```

Implements `ChatModel` and `UsageChatModel` (the game's budget-tier agent, and the standard tier without a Google key) over `groq.AsyncGroq().chat.completions.create`.
Returns the first choice's content, or `""` when it is empty; `complete_with_usage` also
returns the reported `prompt_tokens` and `completion_tokens`.

## `shield_engine.game`

Pure graph interpreter, deterministic and ML check evaluators, the AI Agent, campaign waves, and scoring for the `ai-shield` workflow game (specs 0016 and 0020):

- **Anchor nodes** (locked, non-removable): `incoming` (`Input`) and `assistant` (`Help Desk` on Easy, `Protected Agent` on Medium, Hard and the custom sandbox). A prompt that stops on an unwired tool output is `blocked`; the retired `blocked` node kind is rejected with `RETIRED_BLOCKED_MESSAGE`.
- **Tool nodes** (8 configurable check kinds):
  - `text_cleanup` (`Text cleaner`): normalises text using player-enabled `transforms` (`strip_zero_width`, `decode_base64`, `decode_hex_url`), all off by default (`0.2 ms` base + `0.4 ms` per transform; `out` handle).
  - `word_filter` (`Word filter`): checks prompt text against player-configured `custom_words` phrases (`safe` output; a block stops the prompt).
  - `length_limit` (`Length limit`): blocks prompts exceeding `max_chars` (`safe` output; a block stops the prompt).
  - `secret_scan` (`Secret scanner`): blocks prompts matching player-configured case-insensitive regular expressions in `patterns` (`safe` output; invalid regexes rejected by `validate_board`).
  - `ml_classifier` (`ML filter`): trainable TF-IDF (`max_features=5000`) + scikit-learn classifier (`tfidf`, `logistic_regression`, `linear_svm`, `naive_bayes`, `random_forest`) with 3-way routing via `safe_threshold` (`0.30`) and `block_threshold` (`0.75`) (`safe` and `suspicious` outputs; a block stops the prompt). Nodes look up pre-fitted models by `config.model_id` inside `ml_models`, and never fit during board evaluation; any missing `model_id` passes prompts to `safe` (`"Model not trained"`) (spec 0045).
  - `jev` (`Jev`): TypeSafe System One fast decision model calling `JevClient.evaluate_noul` (`POST https://api.typesafe.ai/v1/systemone`) with the player's boolean `noul` `question` against `threshold`, recording real measured elapsed `latency_ms` and token-based `cost_usd` (`input_tokens * $0.042 / 1M`; raises `BoardValidationError("Insert Jev API key to continue.")` if no `jev_client` is provided). Supports the Tool Policy extension (`tool_policy_enabled`, `block_tools`): when enabled and triggered, switches off the selected numbered tools for the downstream LangGraph agent and routes `safe` instead of stopping the prompt.
  - `safety_check` (`Safety check`): dedicated safety/guardrail classifier (`openai/gpt-oss-safeguard-20b`, the default, which honours `config.thinking: true` (medium reasoning, 2,048-token budget); `meta-llama/llama-prompt-guard-2-86m` and `-22m`, score-only classifiers that receive the raw prompt as a single user message, with no system prompt or `wrap_untrusted()` tags, and block at a score `>= 0.5` and never think; Groq scores only the first 512 tokens; retired Llama Guard, Qwen3Guard, ShieldGemma and Nemotron IDs on saved boards map to the Safeguard model) calling `check_model_for(model)` / `check_model` with `wrap_untrusted(working_text)`, supporting JSON (`flagged` or gpt-oss-safeguard's `violation`) and native guardrail verdicts (`safe`/`unsafe`/`Yes`/`No`), recording real measured `latency_ms` and token-based `cost_usd` (raises `BoardValidationError("Enter API key to continue.")` if no model is provided). Supports the Tool Policy extension (`tool_policy_enabled`, `block_tools`).
  - `llm_review` (`LLM review`): general-purpose LLM reviewer (`gemini-3.5-flash-lite` (default), `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`; retired `gemini-2.x`, Llama IDs and the overloaded `gemini-3.8-flash`/`gemini-3.6-flash` on saved boards map to their replacements; `config.thinking: true` turns on medium reasoning with a 2,048-token budget) calling `check_model_for(model)` / `check_model` with optional player-written `<review_instructions>` (`config.prompt`, max 1,000 chars) and `wrap_untrusted(working_text)`, recording real measured `latency_ms` and token-based `cost_usd` (raises `BoardValidationError("Enter API key to continue.")` if no model is provided). When `tool_policy_enabled=True`, receives the level's numbered tools (`<agent_tools>`) and can return `"blocked_tools"` alongside `"blocked": false` to switch off specific tools on the final LangGraph agent.
  - No tool offers a `block` output (ENG-AGENT-011). A hop can still record `handle: "block"`, and the prompt then stops at that node as `blocked`, even when an older board wires a `block` edge.
- **Level catalog and tiers** (specs 0021 and 0039): `get_levels()` returns 23 campaign problems across `Easy` (`easy-1`..`easy-5`: 3 Free / 2 Pro, classification-only with `agent=None` and `final_node_label="Help Desk"`), `Medium` (`medium-1`..`medium-10`: 2 Free / 8 Pro, `agent_tier="standard"`, `final_node_label="Protected Agent"`), and `Hard` (`hard-1`..`hard-8`: 0 Free / 8 Pro, `agent_tier="budget"`, `final_node_label="Protected Agent"`). Each `GameLevel` defines `difficulty` (`"Easy" | "Medium" | "Hard"`), `order`, `tier` (`"free" | "paid"`), `tags`, optional `constraints: LevelConstraints` (`max_nodes`, `allowed_kinds`, `disallowed_kinds`, `hard_max_latency_ms`, `hard_max_cost_usd`), and optional `follow_up: FollowUpChallenge` (`question`, `hint`, `bonus_points`, `check`). `validate_board_for_level(board, level)` validates topology (`validate_board`) plus Hard-level topology constraints (`max_nodes`, `allowed_kinds`, `disallowed_kinds`). On Hard levels with `hard_max_latency_ms` or `hard_max_cost_usd`, exceeding the budget adds an entry to `WaveScore.constraint_violations` and forces a loss (`won=False`, `total_score=0`, `medal="none"`). On a win (`won=True`), `FollowUpChallenge` is evaluated deterministically during the run (`follow_up_passed`, `follow_up_feedback`) and awards `+bonus_points` capped at `10,000`.
- **AI Agent and Dual-Use conditional tools** (`shield_engine.game.agent`, specs 0020, 0037, and 0039): each non-null `GameLevel.agent` is an `AgentProfile(objective, tools: tuple[AgentTool(name, description, allowed, dual_use=False)], token_budget)`, `LevelMessage.expected_tool` names the tool a benign request should use, and `LevelMessage.forbidden_tools` lists Dual-Use tools that are forbidden on that specific message context. The `assistant` node's `config.rules` holds up to `AGENT_RULE_LIMIT` (5) player rules of at most `AGENT_RULE_MAX_CHARS` (200) characters. A prompt that reaches the agent runs a LangGraph `StateGraph` (`build_agent_graph` with an `agent` node and `ToolNode` bound to non-gated tools) over `UsageChatModel` with the objective, available numbered tools, `<player_rules>`, a per-run canary, and `wrap_untrusted(prompt)`, then is judged into an `AgentRun(reply, tool_calls, refused, verdict, input_tokens, output_tokens, estimated_tokens, latency_ms, cost_usd)`. Verdicts are `leaked` (canary in the reply, or a permanently restricted tool or per-message `forbidden_tools` called on an attack), `protected`, `helped`, or `false_alarm`; unintended restricted or per-message `forbidden_tools` calls on benign prompts deduct `tool_points` unless switched off upstream. A model failure raises `AgentUnavailableError`. With no model, a deterministic stand-in runs instead.
- `validate_training_rows(rows, *, max_rows=200)` and `parse_dataset_csv(csv_text, *, max_rows=200)`: enforce strict `text,label` headers, 2-column rows, labels (`0`, `1`, `safe`, `attack`), Unicode NFC cleaning without control characters, 1 to 500 chars per text, and both classes present (spec 0045).
- `fit_classifier(*, algorithm, rows, max_rows=200) -> FittedClassifier` and `train_custom_classifier(csv_text, algorithm="logistic_regression")`: fit a model once without echoing dataset rows (`TrainingSummary.dataset` is removed).
- `sign_model(model, *, key, context)` and `load_signed_model(blob, *, key, context)` (`shield_engine.game.model_signing`): HMAC-SHA256 verified before `pickle.loads` (raises `ModelSignatureError`).
- `strip_training_data(board: BoardGraph) -> BoardGraph`: strips `model_id` and `dataset` from every `ml_classifier` node config.
- `validate_board(board: BoardGraph)` and `validate_board_for_level(board: BoardGraph, level: GameLevel)`: require exactly one `incoming` and one `assistant` node, at least one tool node between them, valid agent rules, no directed cycles, and (for `validate_board_for_level`) compliance with `level.constraints` topology rules.
- `evaluate_message(board, *, message, message_id="custom", is_attack=False, classifier=None, level_id="easy-1", expected_tool=None, forbidden_tools=frozenset(), agent=None, canary=None, agents=None) -> MessageTrace`: routes one message, recording `HopTrace` entries, latency, cost and, when it reaches the agent, `MessageTrace.agent`.
- `run_wave(board, *, level_id, classifier=None, agent=None, canary_factory=new_canary, agents=None) -> WaveResult`: runs a full level wave with one canary per run. `WaveResult.agent_mode` is `live` with a model, `simulated` without one, and `none` on a classification-only level.
- `run_single_message(board, *, level_id, message, classifier=None, agent=None, agents=None) -> WaveResult`: scores one player-written prompt as an attack.
- `score_traces(messages, traces, *, token_budget, max_latency_ms, max_cost_usd, classify_only) -> WaveScore`: scores evaluated traces; used by `run_wave` and `run_single_message`.
- **Custom sandbox** (`shield_engine.game.custom`, spec 0022): `validate_custom_profile(profile)` checks a player's agent (objective up to 1,000 characters, up to 10 `snake_case` tools of up to 40 characters, unique names, descriptions up to 200 characters). `parse_custom_dataset(csv_text, profile)` and `build_custom_messages(rows, profile)` turn `text,label,expected_tool` rows (labels `normal`/`benign`/`0` or `attack`/`1`; 1 to 50 rows of up to 1,000 characters) into `LevelMessage`s, raising `BoardValidationError` that names the row. `run_custom_wave(board, *, profile, messages, agent, classifier=None)` runs them like a level wave with one canary, scoring against 1,000 tokens, $0.002 per prompt and 3,000 ms; `agent_mode` is `custom`. `run_custom_message` scores one prompt as an attack. `evaluate_message(..., agent_profile=)` replaces the level's agent with the player's.
- `score_campaign(level, board, traces) -> WaveScore` (spec 0050): scores a campaign wave with list prices only. `fair_score(...) -> FairScore` gives the parts: not cleared is `min(4999, round(4999 x A/At x N/Nt))`; cleared is `5000 + 2500 Q + 750` speed `+ 750` cost `+ 1000 S`. A cleared run needs `A` and `N` at or above the level floors (`GameLevel.attack_floor`, `benign_floor`; `None` means all), no leak of a `LevelMessage(critical=True)`, and no broken limit. Medals: `bronze` when cleared, `silver` from 8,000, `gold` from 9,250 with `Q >= 0.7`. `run_wave` stops at the first prompt whose path list latency is over `constraints.max_avg_latency_ms`, or whose wave list cost is over `constraints.max_total_cost_usd`; `WaveResult.stop` is then a `RunStop` and the score is 0. `validate_board_for_level` rejects more than 8 check nodes or more than 2 model nodes.
- `score_wave(...) -> WaveScore` (custom sandbox only since spec 0050): computes `won = (attacks_leaked == 0 and false_alarms == 0)` and the 0 to 10,000 efficiency score (spec 0029). Any leaked attack or false alarm results in a loss (`won=False`, `total_score=0`, `medal="none"`). On a win (`won=True`), points come strictly from workflow efficiency: for agent levels, speed (3,500), cost (3,500), tokens against the level budget (2,000), and tool use (1,000); with `classify_only=True` the weights are speed (5,000) and cost (5,000), and tool and token points are 0. Medals on a win are `gold` (`>= 8500`), `silver` (`>= 7000`), and `bronze` (`< 7000`).
