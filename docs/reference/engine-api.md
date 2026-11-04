# Engine API reference

Public Python API of `shield-engine` (import name `shield_engine`), version 0.1.0.
Source: [`packages/engine/src/shield_engine`](../../packages/engine/src/shield_engine).

All value types are frozen dataclasses with `slots=True`. All enums are `StrEnum`,
so `str(Verdict.SAFE) == "SAFE"`.

- [Top-level exports](#top-level-exports-shield_engine__all__)
- [Enums](#enums)
- [Value types](#value-types)
- [`Shield`](#shield)
- [`ShieldConfig`](#shieldconfig)
- [Ports](#ports)
- [Detectors](#detectors)
- [Adjudication](#adjudication)
- [Policy](#policy)
- [Feedback stores](#feedback-stores)
- [`shield_engine.events`](#shield_engineevents)
- [`shield_engine.models`](#shield_enginemodels)
- [`shield_engine.training`](#shield_enginetraining)
- [`shield_engine.evaluation`](#shield_engineevaluation)
- [`shield_engine.testing`](#shield_enginetesting)
- [`shield_engine.adapters.groq`](#shield_engineadaptersgroq)
- [`shield_engine.game`](#shield_enginegame)

## Top-level exports (`shield_engine.__all__`)

| Symbol | Kind | Defined in |
| --- | --- | --- |
| `Adjudication` | dataclass | `types.py` |
| `Agent` | enum | `types.py` |
| `ChatMessage` | dataclass | `ports.py` |
| `ChatModel` | Protocol | `ports.py` |
| `ClassifierDetector` | class | `detectors/classifier.py` |
| `Clearance` | enum | `types.py` |
| `CsvFeedbackStore` | class | `feedback.py` |
| `DebateAdjudicator` | class | `adjudication/debate.py` |
| `Decision` | dataclass | `types.py` |
| `DecisionLayer` | enum | `types.py` |
| `DialogueTurn` | dataclass | `types.py` |
| `FeedbackStore` | Protocol | `ports.py` |
| `InMemoryFeedbackStore` | class | `feedback.py` |
| `LlamaGuardModerator` | class | `detectors/moderation.py` |
| `ModerationResult` | dataclass | `types.py` |
| `RiskLevel` | enum | `types.py` |
| `ScreeningContext` | dataclass | `types.py` |
| `Shield` | class | `pipeline.py` |
| `ShieldConfig` | dataclass | `config.py` |
| `Signal` | dataclass | `types.py` |
| `Stage` | enum | `types.py` |
| `ToolPolicy` | enum | `types.py` |
| `ToolSpec` | dataclass | `policy.py` |
| `Verdict` | enum | `types.py` |
| `__version__` | `str` | installed distribution version, or `"0.0.0+unknown"` |
| `allowed_tools` | function | `policy.py` |

`Classifier`, `Moderator` and `Adjudicator` are ports that are not re-exported;
import them from `shield_engine.ports`.

## Enums

Full semantics and routing are in [Verdicts and policies](verdicts-and-policies.md).

| Enum | Members (name = value) |
| --- | --- |
| `Verdict` | `SAFE`, `UNCERTAIN`, `MALICIOUS` |
| `ToolPolicy` | `ALLOW_ALL`, `RESTRICTED`, `SHUTDOWN` |
| `RiskLevel` | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `Clearance` | `NONE`, `DENIED`, `GRANTED` |
| `DecisionLayer` | `CLASSIFIER = "LAYER_1_ML"`, `ADJUDICATION = "LAYER_2_DUAL_AGENT"`, `PASSTHROUGH = "SYSTEM"` |
| `Stage` | `CLASSIFIER = "classifier"`, `ADJUDICATION = "adjudication"` |
| `Agent` | `ANALYST`, `WARDEN` |

## Value types

### `Signal`

One detector's opinion.

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `detector` | `str` | required | Detector name (`"classifier"` for Layer 1) |
| `verdict` | `Verdict` | required | |
| `score` | `float` | required | P(malicious) in [0, 1] |
| `override` | `bool` | `False` | `True` when a feedback label decided the verdict |
| `details` | `Mapping[str, Any]` | `{}` | Detector-specific. `ClassifierDetector` sets `sensitive_floor_applied: bool`; a skipped classifier sets `skipped: True` |

### `ModerationResult`

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `flagged` | `bool` | required | |
| `categories` | `tuple[str, ...]` | `()` | e.g. `("S1", "S13")`, or `("ERROR",)` when failing closed |
| `raw` | `str` | `""` | Stripped model reply |
| `error` | `str \| None` | `None` | Exception message when the model call failed |

### `DialogueTurn`

| Field | Type |
| --- | --- |
| `agent` | `Agent` |
| `message` | `str` |
| `timestamp` | `float` (Unix time from `time.time()`) |

### `Adjudication`

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `verdict` | `Verdict` | required | |
| `policy` | `ToolPolicy` | required | Proposed policy (overridden to `SHUTDOWN` by `Shield` when `verdict` is `MALICIOUS`) |
| `confidence` | `float` | required | Clamped to [0, 1] by the debate parser |
| `summary` | `str` | required | Becomes `Decision.reason` |
| `analysis` | `str` | `""` | The first Analyst turn |
| `dialogue` | `tuple[DialogueTurn, ...]` | `()` | |
| `fallback` | `bool` | `False` | `True` when the conservative fallback produced this result |

### `ScreeningContext`

| Field | Type | Default |
| --- | --- | --- |
| `clearance` | `Clearance` | `Clearance.NONE` |

### `Decision`

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `verdict` | `Verdict` | required | Final verdict |
| `policy` | `ToolPolicy` | required | Tool policy the host must enforce |
| `blocked` | `bool` | required | `True` only when `verdict` is `MALICIOUS` |
| `layer` | `DecisionLayer` | required | Layer that produced the decision |
| `reason` | `str` | required | Human-readable reason |
| `classifier` | `Signal` | required | Layer 1 signal (always present) |
| `moderation` | `ModerationResult \| None` | `None` | Present when a moderator is configured |
| `adjudication` | `Adjudication \| None` | `None` | Present when Layer 2 ran (including fallback) |

## `Shield`

```python
Shield(
    classifier: Classifier,
    *,
    moderator: Moderator | None = None,
    adjudicator: Adjudicator | None = None,
    config: ShieldConfig | None = None,   # None -> ShieldConfig()
)
```

Attributes `classifier`, `moderator`, `adjudicator`, `config` hold the constructor values.

| Method | Signature | Returns |
| --- | --- | --- |
| `screen` | `async screen(prompt: str, context: ScreeningContext \| None = None, *, config: ShieldConfig \| None = None)` | `Decision` |
| `screen_stream` | `screen_stream(prompt: str, context: ScreeningContext \| None = None, *, config: ShieldConfig \| None = None)` | `AsyncIterator[ShieldEvent]` |

- `context=None` means `ScreeningContext()` (clearance `NONE`).
- `config` overrides the instance config for this call only.
- `screen()` consumes `screen_stream()` and returns the `Decision` of its `DecisionMade` event.
- Exceptions raised by the classifier or a custom adjudicator propagate.
  `LlamaGuardModerator` and `DebateAdjudicator` catch provider errors themselves.

Event order and routing rules: [Verdicts and policies](verdicts-and-policies.md#routing-table).

## `ShieldConfig`

```python
ShieldConfig(always_adjudicate=False, skip_classifier=False, default_policy=ToolPolicy.ALLOW_ALL)
```

| Field | Type | Default | Effect |
| --- | --- | --- | --- |
| `always_adjudicate` | `bool` | `False` | Send every non-blocked prompt to Layer 2 |
| `skip_classifier` | `bool` | `False` | Do not call the classifier; use `Signal("classifier", SAFE, 0.0, details={"skipped": True})` |
| `default_policy` | `ToolPolicy` | `ALLOW_ALL` | Policy for prompts that were never adjudicated |

## Ports

Structural `typing.Protocol`s in `shield_engine.ports`. Any object with matching
methods satisfies them.

### `ChatMessage`

| Field | Type |
| --- | --- |
| `role` | `Literal["system", "user", "assistant"]` |
| `content` | `str` |

### Protocols

| Protocol | Method |
| --- | --- |
| `ChatModel` | `async complete(messages: Sequence[ChatMessage], *, temperature: float = 0.0, max_tokens: int \| None = None) -> str` |
| `FeedbackStore` | `lookup(text: str) -> int \| None`; `record(text: str, label: int) -> None` (label 1 = malicious) |
| `Classifier` | `score(text: str) -> Signal` (synchronous) |
| `Moderator` | `async moderate(text: str) -> ModerationResult` |
| `Adjudicator` | `adjudicate(prompt: str, clearance: Clearance) -> AsyncIterator[DialogueTurn \| Adjudication]`: yield zero or more turns, then exactly one `Adjudication` |

## Detectors

`shield_engine.detectors` exports `ClassifierDetector`, `LlamaGuardModerator` and
`SENSITIVE_KEYWORDS`.

### `ClassifierDetector`

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
    feedback: FeedbackStore | None = None,
)
```

Raises `ValueError` unless `0 <= safe_threshold < malicious_threshold <= 1`.
Keywords are lower-cased. Class attribute `name = "classifier"`.

| Method | Behaviour |
| --- | --- |
| `score(text) -> Signal` | 1. If `feedback` has a label for the exact text: verdict from the label, score 1.0 or 0.0, `override=True`, model not called. 2. Otherwise `p = predict_proba(transform([text]))[0][1]`. 3. If `p < sensitive_ceiling` and the lower-cased text contains any keyword as a substring, `p = sensitive_floor`. 4. Verdict: `p >= malicious_threshold` MALICIOUS, `p <= safe_threshold` SAFE, else UNCERTAIN. |
| `learn(text, label) -> None` | Records the label in `feedback` (if set) and calls `model.partial_fit(transform([text]), [label])` if the model has `partial_fit` |
| `save_model(path: Path) -> None` | `joblib.dump(model, path)`, creating parent directories |

`SENSITIVE_KEYWORDS`: `sales`, `revenue`, `employee`, `salary`, `database`, `sql`,
`delete`, `personal`, `customer`, `member`, `boss`, `org`, `chart`, `hierarchy`,
`email`, `private`, `confidential`, `internal`, `table`, `drop`.

### `LlamaGuardModerator`

```python
LlamaGuardModerator(model: ChatModel, *, fail_closed: bool = False)
```

`async moderate(text) -> ModerationResult` sends one user message with
`temperature=0.0, max_tokens=64`.

| Model reply / outcome | Result |
| --- | --- |
| First line is `safe` (case-insensitive) | `flagged=False`, `raw` set |
| Anything else | `flagged=True`, `categories` = remaining lines split on commas and newlines |
| Exception, `fail_closed=False` | `flagged=False`, `categories=()`, `error=str(exc)` |
| Exception, `fail_closed=True` | `flagged=True`, `categories=("ERROR",)`, `error=str(exc)` |

## Adjudication

`shield_engine.adjudication` exports `DebateAdjudicator`, `fallback_adjudication`
and `parse_warden_verdict`.

### `DebateAdjudicator`

```python
DebateAdjudicator(model: ChatModel, *, temperature: float = 0.3)
```

`adjudicate(prompt, clearance)` makes four `model.complete` calls (system + user
message each): Analyst, Warden, Analyst (each yielded as a `DialogueTurn`), then a
final Warden call that must answer with JSON
`{"verdict", "policy", "confidence", "summary"}`. It yields one `Adjudication`
with `analysis` set to the first Analyst message and `dialogue` set to the three turns.

- The prompt is wrapped in `<untrusted_prompt>…</untrusted_prompt>`; any
  opening or closing look-alike tag inside the prompt or earlier turns is replaced
  with `[delimiter removed]`.
- Clearance is sent as the words `GRANTED` or `DENIED` only. `Clearance.NONE`
  is described to the model as `DENIED`.
- Any exception during the four calls yields
  `fallback_adjudication(clearance, "Adjudicator unavailable; conservative policy applied.", turns_so_far)`.

### `wrap_untrusted(prompt: str) -> str`

Importable from `shield_engine.adjudication`. Returns
`"<untrusted_prompt>\n{prompt}\n</untrusted_prompt>"` with look-alike tags in
`prompt` neutralised. Any engine code that sends user text to an LLM must use it.

### `parse_warden_verdict(raw: str, clearance: Clearance) -> Adjudication`

Extracts the outermost `{…}` from `raw`. Missing or invalid JSON, a non-object, or
a `verdict`/`policy` outside the enums yields
`fallback_adjudication(clearance, "Warden output was unusable; fallback applied.")`.
`confidence` defaults to 0.5, is clamped to [0, 1], and non-numeric values become 0.5.
Missing `summary` becomes `"Dual agent review completed."`.

### `fallback_adjudication(clearance, summary, dialogue=()) -> Adjudication`

| Clearance | verdict | policy |
| --- | --- | --- |
| `GRANTED` | `SAFE` | `ALLOW_ALL` |
| `NONE` or `DENIED` | `UNCERTAIN` | `RESTRICTED` |

Always `confidence=0.5`, `fallback=True`. Never blocks.

## Policy

| Symbol | Signature |
| --- | --- |
| `ToolSpec` | dataclass `ToolSpec(name: str, risk: RiskLevel)` |
| `allowed_tools` | `allowed_tools(policy: ToolPolicy, tools: Iterable[ToolSpec]) -> list[str]` |

`ALLOW_ALL` returns every name, `RESTRICTED` only `LOW`-risk names, `SHUTDOWN`
an empty list. Input order is preserved.

## Feedback stores

| Class | Constructor | Behaviour |
| --- | --- | --- |
| `InMemoryFeedbackStore` | `(labels: dict[str, int] \| None = None)` | Dict lookup; copies `labels` |
| `CsvFeedbackStore` | `(path: Path)` | Reads the CSV once at construction (latest label per text wins). `record()` appends a row `text,label,timestamp` (UTC ISO 8601), writing the header and parent directories if needed, and updates the cache |

## `shield_engine.events`

Events yielded by `Shield.screen_stream`. All are frozen dataclasses.

| Event | Field | Emitted |
| --- | --- | --- |
| `StageStarted` | `stage: Stage` | Before Layer 1 (`CLASSIFIER`) and before Layer 2 (`ADJUDICATION`) |
| `ClassifierScored` | `signal: Signal` | After Layer 1, always |
| `ModerationFlagged` | `result: ModerationResult` | Only when the moderator flags the prompt |
| `DebateTurn` | `turn: DialogueTurn` | For each turn the adjudicator yields |
| `DecisionMade` | `decision: Decision` | Exactly once, last |

`ShieldEvent` is the type alias
`StageStarted | ClassifierScored | ModerationFlagged | DebateTurn | DecisionMade`.

## `shield_engine.models`

| Symbol | Description |
| --- | --- |
| `BASELINE_DIR` | `Path` of the bundled `models/baseline/` directory |
| `MODEL_FILE`, `VECTORIZER_FILE`, `METADATA_FILE` | `"model.joblib"`, `"vectorizer.joblib"`, `"metadata.json"` |
| `ArtifactIntegrityError` | `RuntimeError` subclass: artifact or metadata missing, or digest mismatch |
| `sha256_file(path: Path) -> str` | Hex SHA-256 of a file |
| `read_metadata(directory: Path = BASELINE_DIR) -> dict` | Parses `metadata.json`; raises `ArtifactIntegrityError` if missing |
| `verify_artifacts(directory: Path = BASELINE_DIR) -> dict` | Checks every entry of `metadata["files"]` against its SHA-256; returns the metadata or raises `ArtifactIntegrityError` |
| `load_baseline(*, directory: Path = BASELINE_DIR, **kwargs) -> ClassifierDetector` | Verifies, then `joblib.load`s vectorizer and model; `kwargs` go to `ClassifierDetector` |

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

## `shield_engine.evaluation`

| Symbol | Signature / fields |
| --- | --- |
| `Example` | dataclass `Example(text: str, label: int, source: str \| None = None, category: str \| None = None)`; label 1 = malicious |
| `DatasetError` | `ValueError` subclass; message names the file and 1-based line |
| `load_jsonl(path: Path) -> list[Example]` | Skips blank lines. Raises `DatasetError` on invalid JSON, a non-object row, non-string `text`, or `label` not exactly `0` or `1` (booleans rejected) |
| `BinaryMetrics` | dataclass `(tp, fp, tn, fn)` with properties `precision`, `recall`, `f1`, `false_positive_rate`, `accuracy` (0.0 on a zero denominator) and `as_dict()` |
| `compute_metrics(y_true, y_pred) -> BinaryMetrics` | Raises `ValueError` if lengths differ |
| `EvaluationReport` | dataclass `(metrics, examples, abstention_rate, latency_ms_p50, latency_ms_p95)` with `as_dict()` |
| `evaluate(shield, examples, context=None) -> EvaluationReport` | async. Screens sequentially; blocked = predicted 1; abstention = share of `UNCERTAIN` verdicts |

`EvaluationReport.as_dict()` shape:
`{"examples", "metrics": {tp, fp, tn, fn, precision, recall, f1, false_positive_rate, accuracy}, "abstention_rate", "latency_ms": {"p50", "p95"}}`.

## `shield_engine.testing`

Deterministic doubles, shipped in the package for host tests. All are mutable
dataclasses that record their calls.

| Class | Fields (default) | Behaviour |
| --- | --- | --- |
| `StaticClassifier` | `verdict=SAFE`, `probability=0.05`, `calls=[]`, `learned=[]` | `score()` returns `Signal("classifier", verdict, probability)`; `learn()` appends to `learned` |
| `StaticModerator` | `result=ModerationResult(flagged=False)`, `calls=[]` | `moderate()` returns `result` |
| `ScriptedAdjudicator` | `verdict=SAFE`, `policy=RESTRICTED`, `summary="scripted adjudication"`, `turns=((ANALYST, "looks fine"),)`, `calls=[]` | Yields each turn, then `Adjudication(verdict, policy, 0.9, summary, dialogue=…)`; records `(prompt, clearance)` |
| `ScriptedChatModel` | `replies: list[str \| BaseException]` (required), `calls=[]` | Pops replies in order; raises a queued exception; raises `AssertionError` when empty |

## `shield_engine.adapters.groq`

Requires the `groq` extra (`shield-engine[groq]`); importing the module without it
raises `ImportError`.

```python
GroqChatModel(api_key: str, model: str, *, timeout: float = 30.0)
```

Implements `ChatModel` over `groq.AsyncGroq().chat.completions.create`. Returns
the first choice's content, or `""` when it is empty.

## `shield_engine.game`

Pure graph interpreter, deterministic and ML check evaluators, campaign waves, and scoring engine for the `ai-shield` workflow game (spec 0011):

- **Anchor nodes** (locked, non-removable): `incoming` (`Input`), `assistant` (`Safe` on Easy, `Assistant` on Medium/Hard), and `blocked` (`Blocked`).
- **Tool nodes** (9 configurable check kinds):
  - `text_cleanup` (`Text cleaner`): strips zero-width Unicode characters, normalises compatibility glyphs, and decodes Base64 spans (`out` handle).
  - `word_filter` (`Word filter`): checks prompt text against rule groups (`override`, `encoded`, `sql_tools`) and custom blocked phrases (`safe` or `block` handle).
  - `length_limit` (`Length limit`): blocks prompts exceeding `max_chars` (`safe` or `block` handle).
  - `secret_scan` (`Secret scanner`): blocks API keys, tokens, private keys, and internal credentials (`safe` or `block` handle).
  - `ml_classifier` (`ML filter`): custom TF-IDF + scikit-learn classifier trained on player-uploaded CSV (`text,label`) with selectable algorithm (`logistic_regression`, `linear_svm`, `naive_bayes`, `random_forest`) and risk threshold (`safe` or `block` handle).
  - `quick_screen` (`Quick screen`): bundled Layer 1 TF-IDF classifier with configurable `safe_threshold` and `block_threshold` (`safe`, `suspicious`, `block` handles).
  - `safety_check` (`Safety check`): Llama Guard moderation check (`safe` or `block` handle).
  - `agent_review` (`Agent review`): Analyst/Warden dual-agent debate (`safe` or `block` handle).
  - `tool_filter` (`Tool filter`): deterministic tool-access policy gate (`out` handle).
- `train_custom_classifier(csv_text, algorithm="logistic_regression")`: parses `text,label` CSV data, trains the chosen algorithm, and returns training accuracy and serialised dataset rows.
- `validate_board(board: BoardGraph)`: validates anchor nodes, ensures at least one tool node is wired between `incoming` and `assistant`/`blocked`, rejects directed cycles, and enforces max node limits.
- `run_game_wave(...)` / `evaluate_board_message(...)`: runs a single test message or a full level wave through a `BoardGraph`, recording `HopTrace` entries, latency, and cost.
- `score_wave(...) -> WaveScore`: computes the 0 to 10,000 point breakdown across protection (0 to 5,000), false alarms (0 to 2,000), speed (0 to 1,500), and cost (0 to 1,500), plus medal (`gold`, `silver`, `bronze`, `none`).
