# 0030 — Tool refinements (Text cleaner, regex Secret scanner, conditional Tool filter) and Jev

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-17
- **Related:** [0029-strict-win-lose-and-tool-config](../0029-strict-win-lose-and-tool-config/spec.md), [0020-game-ai-agent](../0020-game-ai-agent/spec.md)

## Problem

1. **`text_cleanup` still runs a built-in preset.** Dropping a `text_cleanup` node automatically strips zero-width characters and decodes Base64 with no player configuration.
2. **`secret_scan` only supports plain substrings.** Players cannot write regular expressions (such as `sk-[a-z0-9]{8,}` or `password|secret\s+code`) to match structured secrets or patterns.
3. **`tool_filter` acts like a duplicate word filter instead of gating the AI Agent's tools.** When an AI Agent has specific tools (`level.agent.tools`), `tool_filter` should let the player select which agent tools to block and under what condition (`always` or when the prompt matches a regex/keyword `pattern`), and prevent the Protected Agent from invoking blocked tools.
4. **Missing a fast System One decision model (`jev`).** Between static/local filters (`0.2–4.5 ms`, `$0`) and heavy generative LLM checks (`safety_check` at `85 ms / $0.0002`, `agent_review` at `920 ms / $0.0030`), the palette lacks **Jev** (TypeSafe AI's System One decision engine), which evaluates a player-written boolean `noul` question in a single parallel pass (`12 ms`, `$0.00005`) and returns a calibrated probability against a player-configured risk threshold.

## Goals

- Require players to toggle which `text_cleanup` transforms run (`strip_zero_width`, `decode_base64`, `decode_hex_url`), all off by default, with latency scaling by the number of enabled transforms (`0.2 ms` base + `0.4 ms` per transform).
- Support case-insensitive regular expressions in `secret_scan` `config.patterns` and reject invalid regexes during `validate_board`.
- Redesign `tool_filter` around the Protected Agent's tools: players configure rules `{ tool, condition: "always" | "match", pattern }`. Matching rules block the prompt at `tool_filter`, and `"always"` rules also strip/block that tool if a prompt reaches the Protected Agent (blocking an allowed `expected_tool` causes a false alarm, preventing blanket blocks).
- Add the `jev` check node (`12.0 ms`, `$0.00005`, `handles=("safe",)`) where players write a boolean `noul` question (`config.question`) and risk `config.threshold` (`0.05..0.95`, default `0.70`).

## Non-goals

- Calling an external paid TypeSafe API over the network during offline/standard wave runs (`jev` runs deterministically in the engine and is available as a fast System One guardrail).
- Changing the strict Win/Lose scoring rules introduced in Spec 0029.

## Behaviour

### 1. Text cleaner (`text_cleanup`)

- Configurable `config.transforms`: list of `"strip_zero_width" | "decode_base64" | "decode_hex_url"`.
- Default when newly placed (`config.transforms` omitted or `[]` in UI): no transforms enabled (`was_modified = False`, latency `0.2 ms`).
- Latency: `0.2 + 0.4 * len(enabled_transforms)` ms (`$0` cost).
- Transform behaviours:
  - `strip_zero_width`: removes `[\u200b\u200c\u200d\ufeff]`.
  - `decode_base64`: unpacks inline Base64 tokens (`[unpacked: ...]`).
  - `decode_hex_url`: unpacks URL percent-encoding (`%xx`) and `\xNN` hex sequences (`[unpacked: ...]`).

### 2. Secret scanner (`secret_scan`)

- `config.patterns`: list of regular expression strings, evaluated with `re.search(pattern, working_text, re.IGNORECASE)`.
- `validate_board` compiles each pattern in `config.patterns` and raises `BoardValidationError` if any pattern is an invalid regular expression.

### 3. Tool filter (`tool_filter`)

- `config.rules`: list of `{ "tool": str, "condition": "always" | "match", "pattern": str }` (legacy `config.blocked_tools: list[str]` continues to work as `condition="match", pattern=tool`).
- When a message visits `tool_filter`:
  - For each rule:
    - If `condition == "always"`: if `tool.lower()` appears in `working_text.lower()`, blocks at `tool_filter` (`handle = "block"`), and records `tool` in the message's active blocked-tool set for downstream `assistant` execution.
    - If `condition == "match"` and `pattern.strip()`: if `re.search(pattern, working_text, re.IGNORECASE)` matches, blocks at `tool_filter` (`handle = "block"`).
- When a message reaches `assistant`:
  - Any tool in the active blocked-tool set cannot be executed by the Protected Agent:
    - If an attack prompt would have leaked via a forbidden tool call that is in the blocked-tool set, the call is blocked by the tool policy gate and the verdict becomes `"protected"`.
    - If a benign prompt requires `expected_tool` and that tool is in the blocked-tool set, the tool call is blocked and the verdict becomes `"false_alarm"`.

### 4. Jev (`jev`)

- Catalog entry: `kind="jev"`, `label="Jev"`, `summary="System One fast decision model using a boolean noul question."`, `handles=("safe",)`, `latency_ms=12.0`, `cost_usd=0.00005`.
- Configuration:
  - `question: str` (default `""`, max 300 chars; validated in `validate_board`).
  - `threshold: float` (default `0.70`, range `0.05..0.95`).
- Evaluation:
  - If `question.strip()` is empty, `jev` outputs `handle = "safe"`, `detail = "No noul question configured"`.
  - Otherwise, `jev` computes `noul(working_text, question, cleaned=cleaned) -> float` in `[0.0, 1.0]` based on which threat categories the `question` asks about (`override`/instructions/prompt, `jailbreak`/roleplay/dan/hypothetical, `secret`/password/salary/code/confidential, `tool`/sql/payroll/transfer/logs/database, `encoded`/base64/hidden) and whether `working_text` exhibits those signals.
  - If `prob >= threshold`, `handle = "block"`, `detail = f"Jev noul: {prob * 100:.0f}% >= {threshold * 100:.0f}%"`; otherwise `handle = "safe"`, `detail = f"Jev noul: {prob * 100:.0f}% < {threshold * 100:.0f}%"`.

## Acceptance criteria

- **ENG-TOOL-006**: Given a `text_cleanup` node with `transforms=[]`, when a prompt with zero-width characters or Base64 is evaluated, then `text_cleanup` leaves the text unchanged with `0.2 ms` latency; when `transforms` includes `"strip_zero_width"`, `"decode_base64"`, or `"decode_hex_url"`, then only the selected transforms run and latency scales by `0.2 + 0.4 * count` ms.
- **ENG-TOOL-007**: Given a `secret_scan` node configured with regex `patterns` (e.g. `r"sk-[a-z0-9]{6,}"` or `r"secret\s+discount"`), when a matching prompt is evaluated, then `secret_scan` blocks it; when `patterns` contains an invalid regex (e.g. `"[unclosed"`), then `validate_board` raises `BoardValidationError`.
- **ENG-TOOL-008**: Given a `tool_filter` node with per-tool `rules`, when `condition` is `"match"` and the prompt matches `pattern`, then `tool_filter` blocks at the node; when `condition` is `"always"`, then `tool_filter` prevents the downstream Protected Agent from calling that tool (protecting against forbidden tool leaks, or causing a `false_alarm` if a required allowed tool is blocked).
- **ENG-TOOL-009**: Given a `jev` node, when `question` is empty, then it passes prompts to `safe`; when `question` asks a boolean `noul` question covering the attack category and the computed probability meets `threshold`, then `jev` blocks the attack in `12.0 ms` at `$0.00005`.
- **API-TOOL-001**: Given `GET /api/v1/game/levels` and `POST /api/v1/game/run`, when called with a board containing `jev`, regex `secret_scan`, conditional `tool_filter`, and `text_cleanup` transforms, then `jev` is listed in `checks`, invalid regexes return `422`, and valid boards evaluate and return traces.
- **WEB-TOOL-001**: Given `/game` and `NODE_CATALOG`, when inspecting tools and opening node settings modals, then `jev` is present in the tool palette and modal (`question` and `threshold`), `text_cleanup` shows transform toggles (off by default), `secret_scan` accepts regex patterns, and `tool_filter` configures conditions (`always` or `match`) for the level's agent tools.

## Security & privacy considerations

- User-supplied regex patterns in `secret_scan` and `tool_filter` are length-capped (`<= 200` chars) and validated with `re.compile` during `validate_board`.
- `jev` evaluates `working_text` deterministically without interpolating untrusted text into privileged system instructions.

## Evaluation impact

- Adds `jev` (`12.0 ms`, `$0.00005`) as a fast System One middle tier between local classifiers (`3.8–4.5 ms`, `$0`) and generative LLM checks (`85–920 ms`, `$0.0002–$0.0030`).

## Open questions

- None.

## Verification

### 2026-11-17 · commit 2a0b84f (+ uncommitted changes)

- Criteria: ENG-TOOL-006, ENG-TOOL-007, ENG-TOOL-008, ENG-TOOL-009, API-TOOL-001, WEB-TOOL-001
- Red: 6 failing test(s) before implementation (`packages/engine/tests/test_game.py::test_text_cleanup_requires_explicit_transforms_and_scales_latency`, `packages/engine/tests/test_game.py::test_secret_scan_supports_regex_patterns_and_rejects_invalid_regex`, `packages/engine/tests/test_game.py::test_tool_filter_evaluates_per_tool_conditions_and_gates_agent_tools`)
- Green: 6 passing test(s)
- Gate: `mise run check` passed
