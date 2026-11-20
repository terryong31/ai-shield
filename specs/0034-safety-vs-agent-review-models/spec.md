# 0034 — Distinct Safety check (guardrail models) vs Agent review (LLM + custom prompt)

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-17
- **Related:** [0031-live-api-keys-and-real-metrics](../0031-live-api-keys-and-real-metrics/spec.md)

## Problem

`safety_check` and `agent_review` currently present identical UI (the same 4-button model grid combining `gpt-4o-mini`, `llama-3.3-70b-versatile`, `llama-guard-3-8b`, and `gemini-2.0-flash`) and neither lets the player supply review instructions for `agent_review`. They should be fundamentally distinct tools:
- **Safety check (`safety_check`)**: uses **only safety/guardrail-specific models** (e.g. Llama Guard, Qwen3Guard, ShieldGemma, Nemotron Safety Guard) picked via `USelectMenu`.
- **Agent review (`agent_review`)**: uses **general-purpose LLMs** picked via `USelectMenu` **and** lets the player write custom review instructions (`config.prompt`) for the LLM.

## Goals

- Restrict `safety_check` model choices to dedicated safety/guardrail models (`llama-guard-3-8b`, `meta-llama/llama-guard-4-12b`, `qwen3guard-8b`, `shieldgemma-9b`, `llama-nemotron-safety-guard-8b`) and handle both JSON and guardrail-native verdicts (`safe` / `unsafe` / `Yes` / `No`).
- Restrict `agent_review` model choices to general-purpose LLMs (`gemini-2.5-flash`, `gemini-2.0-flash`, `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `gpt-4o-mini`) and allow the player to enter a custom review prompt/instruction (`config.prompt`, max 1,000 chars) that guides the reviewer LLM.
- Replace the 4-button grid in both modals with `<USelectMenu>`.
- Route `node.config.model` to the matching `.env`-configured backend provider (`GeminiChatModel` / `GroqChatModel`) when available.

## Non-goals

- Adding a new node kind or changing the strict zero-leak scoring rules.

## Behaviour

- **Safety check (`safety_check`)**:
  - Default `model`: `"llama-guard-3-8b"`.
  - Allowed catalog in UI (`USelectMenu`):
    - `llama-guard-3-8b` (Llama Guard 3 8B)
    - `meta-llama/llama-guard-4-12b` (Llama Guard 4 12B)
    - `qwen3guard-8b` (Qwen3Guard 8B)
    - `shieldgemma-9b` (ShieldGemma 9B)
    - `llama-nemotron-safety-guard-8b` (Nemotron Safety Guard 8B)
  - Validation: rejects non-safety models if configured on `safety_check`? Wait: legacy saves might have `gpt-4o-mini`; engine normalizes or evaluates cleanly while UI exposes only the safety models (`USelectMenu`).
  - Verdict parsing: treats JSON `{"flagged": true}` **or** plain-text guardrail verdicts starting with `"unsafe"` or `"yes"` as `block`; otherwise `safe`.
- **Agent review (`agent_review`)**:
  - Default `model`: `"gemini-2.5-flash"`, default `prompt`: `""`.
  - Allowed catalog in UI (`USelectMenu`):
    - `gemini-2.5-flash` (Gemini 2.5 Flash)
    - `gemini-2.0-flash` (Gemini 2.0 Flash)
    - `llama-3.3-70b-versatile` (Llama 3.3 70B Versatile)
    - `llama-3.1-8b-instant` (Llama 3.1 8B Instant)
    - `gpt-4o-mini` (GPT-4o mini)
  - Player prompt (`config.prompt`, up to 1,000 chars, validated in `validate_board`): included inside `<review_instructions>` in the system prompt sent to the reviewer LLM alongside `wrap_untrusted(working_text)`.

## Acceptance criteria

- **ENG-CHECK-001**: Given a `safety_check` node, when evaluated against a guardrail response (`"unsafe\nS1"` or `{"flagged": true}`), then `safety_check` blocks the prompt; when given `"safe"` or `{"flagged": false}`, it routes to `safe`; and `check_model_for(model)` routes the configured model when provided.
- **ENG-CHECK-002**: Given an `agent_review` node with `config.prompt` set, when evaluated, then the player's review instructions are included in the system message sent to the reviewer LLM while user text remains wrapped in `wrap_untrusted()`; when `len(prompt) > 1000`, `validate_board` raises `BoardValidationError`.
- **WEB-CHECK-001**: Given `/game` node settings modals, when opening `safety_check` or `agent_review`, then both render a `<USelectMenu>` for model selection (`safety_check` listing only safety/guardrail models like Llama Guard, Qwen3Guard, ShieldGemma, Nemotron Safety Guard; `agent_review` listing general LLMs plus a `<UTextarea>` for the review prompt/instruction).

## Security & privacy considerations

- Player-written `agent_review` instructions stay in the system prompt while untrusted prompt input stays isolated in `wrap_untrusted()`.

## Evaluation impact

- None.

## Open questions

- None.

## Verification

### 2026-11-17 · commit 2a0b84f (+ uncommitted changes)

- Criteria: ENG-CHECK-001, ENG-CHECK-002, WEB-CHECK-001
- Red: 3 failing test(s) before implementation (`packages/engine/tests/test_game.py::test_safety_check_supports_guardrail_verdicts_and_model_routing`, `packages/engine/tests/test_game.py::test_agent_review_includes_custom_prompt_and_validates_length`, `design hygiene and anti-slop copy standard [WEB-CHECK-001] distinguishes safety_check (guardrail USelectMenu) from agent_review (LLM USelectMenu + prompt)`)
- Green: 3 passing test(s)
- Gate: `mise run check` passed
