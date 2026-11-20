# 0031 — Live Jev & AI node API keys and real measured latency/cost

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-17
- **Related:** [0030-tool-refinements-and-jev](../0030-tool-refinements-and-jev/spec.md), [0029-strict-win-lose-and-tool-config](../0029-strict-win-lose-and-tool-config/spec.md), [0022-game-custom-sandbox](../0022-game-custom-sandbox/spec.md)

## Problem

1. **`jev`, `safety_check`, and `agent_review` still use simulated local evaluation.** In `shield_engine.game`, `jev` computes a local heuristic score instead of calling TypeSafe's `POST https://api.typesafe.ai/v1/systemone` API, and `safety_check` / `agent_review` match hardcoded keyword lists instead of calling an LLM.
2. **Nodes are not gated when API keys are missing.** If no Jev API key (`TYPESAFE_API_KEY` or player-supplied key) is configured, the `Jev` node should be disabled and prompt `"Insert Jev API key to continue"`. Likewise, if no AI API key (`GROQ_API_KEY` / `GOOGLE_API_KEY` or player-supplied key) is configured, `Safety check` and `Agent review` should be disabled and prompt `"Enter API key to continue"`.
3. **Latency and cost are hardcoded estimates instead of real backend measurements.** Every check hop currently records fixed constants (`0.4 ms`, `12.0 ms`, `85.0 ms`, `$0.0002`, etc.) rather than measuring actual execution time (`time.perf_counter()`) and computing real token cost in the backend and returning those actual metrics to the frontend.

## Goals

- Remove simulated local evaluation for `jev`, `safety_check`, and `agent_review`; execute them via real ports (`JevClient` and `UsageChatModel`) injected by the gateway.
- Require a Jev API key (from backend `TYPESAFE_API_KEY` or player input) to place/run `jev`, disabling the node in the UI with `"Insert Jev API key to continue"` when missing.
- Require an AI API key (from backend `GROQ_API_KEY` / `GOOGLE_API_KEY` or player input) to place/run `safety_check` and `agent_review`, disabling the nodes in the UI with `"Enter API key to continue"` when missing.
- Measure real wall-clock latency (`time.perf_counter()`) and compute real token-based cost in the backend for every hop during workflow execution, returning the actual `latency_ms` and `cost_usd` in `HopTrace`, `MessageTrace`, and `WaveScore`.

## Non-goals

- Persisting player-entered API keys to SQLite or Supabase (keys stay in memory for the session/request only and are never logged or echoed).
- Changing the strict zero-leak / zero-false-alarm Win/Lose rules from Spec 0029.

## Behaviour

### 1. Real `JevClient` and `UsageChatModel` execution (`packages/engine`)

- **`JevClient` port (`shield_engine.ports`)**:
  - `JevEvaluation(probability: float, input_tokens: int, output_tokens: int)`
  - `JevClient.evaluate_noul(state: str, question: str, *, model: str = "jev-latest") -> JevEvaluation`
- **`jev` node in `evaluate_message`**:
  - Requires `jev_client: JevClient | None` when a `jev` node is reached (or present on the board). If `jev_client is None`, raises `BoardValidationError("Insert Jev API key to continue.")`.
  - Calls `await jev_client.evaluate_noul(working_text, question)`, measures real elapsed `latency_ms` via `time.perf_counter()`, and computes real `cost_usd = round(res.input_tokens * 0.042 / 1_000_000, 8)` (TypeSafe Jev pricing: `$0.042 / 1M` input tokens, `$0` output tokens).
- **`safety_check` and `agent_review` nodes in `evaluate_message`**:
  - Require `check_model: UsageChatModel | None` (falling back to `agent` / `model` when provided). If no `UsageChatModel` is available, raises `BoardValidationError("Enter API key to continue.")`.
  - Wrap `working_text` with `wrap_untrusted(working_text)` and call `complete_with_usage`:
    - `safety_check`: single-pass prompt-injection / jailbreak review returning JSON `{"flagged": bool, "reason": str}`.
    - `agent_review`: dual-role Analyst + Warden review returning JSON `{"blocked": bool, "reason": str}`.
  - Measure real elapsed `latency_ms` via `time.perf_counter()` and compute real `cost_usd` from reported `input_tokens` and `output_tokens` using the selected model's per-token pricing.
- **All other nodes (`incoming`, `text_cleanup`, `length_limit`, `secret_scan`, `word_filter`, `ml_classifier`, `quick_screen`, `tool_filter`)**:
  - Measure actual execution time in the backend via `time.perf_counter()` (`latency_ms = round((time.perf_counter() - started) * 1000, 2)`) with `cost_usd = 0.0`.

### 2. Gateway API key detection & per-run keys (`apps/api`)

- `Settings` adds `TYPESAFE_API_KEY: SecretStr | None` (alias `JEV_API_KEY`).
- `GET /api/v1/game/levels` (`GameCatalogResponse`) adds:
  - `jev_key_configured: bool` (`True` when `settings.TYPESAFE_API_KEY` is set)
  - `ai_key_configured: bool` (`True` when `settings.GROQ_API_KEY` or `settings.GOOGLE_API_KEY` is set)
- `POST /api/v1/game/run` (`GameRunRequest`) accepts optional per-run keys:
  - `jev_api_key: SecretStr | None = None`
  - `ai_api_key: SecretStr | None = None`
  - `ai_provider: ProviderId = "openai"`
- `HttpJevClient` (`shield_api.providers.typesafe`) calls `POST https://api.typesafe.ai/v1/systemone` with `Authorization: Bearer <key>`, mapping `401/403` to `ProviderAuthError` (`502`) and network/5xx errors to `ProviderUnavailableError` (`503`), never logging or echoing the key.

### 3. Web UI key gating & real metrics (`apps/web`)

- `canUseNodeKind(kind, session, keys)`:
  - For `jev`: disabled if neither `jevKeyConfigured` nor player `jevApiKey` is present; shows `"Insert Jev API key to continue"` and opens a modal/input to enter the Jev API key.
  - For `safety_check` and `agent_review`: disabled if neither `aiKeyConfigured` nor player `aiApiKey` is present; shows `"Enter API key to continue"` and opens a modal/input to enter the AI provider & API key.
- Node cards and modals display real backend-measured latency and cost from the latest run (`hop.latency_ms` and `hop.cost_usd`).

## Acceptance criteria

- **ENG-LIVE-001**: Given a board with a `jev` node, when `evaluate_message` runs without a `jev_client`, then it raises `BoardValidationError` with `"Insert Jev API key to continue"`; when `jev_client` is provided, then it calls `jev_client.evaluate_noul`, blocks when `probability >= threshold`, and records real measured `latency_ms` and token-based `cost_usd`.
- **ENG-LIVE-002**: Given a board with `safety_check` or `agent_review`, when `evaluate_message` runs without a `check_model` (or `agent`), then it raises `BoardValidationError` with `"Enter API key to continue"`; when `check_model` is provided, then it calls `complete_with_usage` with `wrap_untrusted(working_text)` and records real measured `latency_ms` and token-based `cost_usd`.
- **ENG-LIVE-003**: Given any board evaluation in `evaluate_message`, when hops are recorded, then every hop's `latency_ms` is measured from actual backend execution time (`time.perf_counter()`) rather than a hardcoded constant.
- **API-LIVE-001**: Given `GET /api/v1/game/levels` and `POST /api/v1/game/run`, when called, then `/levels` reports `jev_key_configured` and `ai_key_configured`, `/run` accepts `jev_api_key` and `ai_api_key` without leaking them in responses or logs, and returns `422` when a board uses `jev` or AI nodes without a configured or supplied key.
- **WEB-LIVE-001**: Given `/game` when no Jev API key is detected, then the `jev` node is disabled and shows `"Insert Jev API key to continue"` with an input to supply the key; when no AI API key is detected, then `safety_check` and `agent_review` are disabled and show `"Enter API key to continue"` with an input to supply the key.

## Security & privacy considerations

- All prompts sent to `check_model` in `safety_check` and `agent_review` wrap user text with `wrap_untrusted()`.
- Player-supplied `jev_api_key` and `ai_api_key` are wrapped in `SecretStr`, never logged, never stored in SQLite/Supabase, and never echoed in HTTP error responses.

## Evaluation impact

- Latency and cost in `HopTrace`, `MessageTrace`, and `WaveScore` now reflect real backend execution time and actual API token usage.

## Open questions

- None.

## Verification

### 2026-11-17 · commit 2a0b84f (+ uncommitted changes)

- Criteria: ENG-LIVE-001, ENG-LIVE-002, ENG-LIVE-003, API-LIVE-001, WEB-LIVE-001
- Red: 5 failing test(s) before implementation (`packages/engine/tests/test_game.py::test_jev_node_evaluates_boolean_noul_question_against_threshold`, `packages/engine/tests/test_game.py::test_safety_check_and_agent_review_require_check_model_and_compute_real_token_cost`, `packages/engine/tests/test_game.py::test_all_hops_record_measured_backend_latency_rather_than_static_constants`)
- Green: 5 passing test(s)
- Gate: `mise run check` passed

### 2026-11-17 · commit 2a0b84f (+ uncommitted changes)

- Criteria: WEB-LIVE-001
- Red: 1 failing test(s) before implementation (`design hygiene and anti-slop copy standard [WEB-LIVE-001] disables Jev and AI nodes when API keys are missing and prevents placing them in the workflow`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed
