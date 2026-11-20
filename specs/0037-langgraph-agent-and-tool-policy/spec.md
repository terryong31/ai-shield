# 0037 — LangGraph AI Agent and Tool Policy extension

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-18
- **Related:** [0020-game-ai-agent](../0020-game-ai-agent/spec.md), [0029-strict-win-lose-and-tool-config](../0029-strict-win-lose-and-tool-config/spec.md), [0030-tool-refinements-and-jev](../0030-tool-refinements-and-jev/spec.md), [0034-safety-vs-agent-review-models](../0034-safety-vs-agent-review-models/spec.md)

## Problem

1. **The final AI Agent is not built with LangGraph.** Real-world AI agents use stateful tool-calling graphs (such as LangGraph `StateGraph` with an `agent` node and `ToolNode` bound to actual tool schemas), whereas `shield_engine.game.agent` currently uses a custom single-turn prompt asking the LLM to echo JSON tool names and listing restricted tools as "never call these". As a result, the final agent does not behave like a real tool-calling agent that can be genuinely tricked into invoking available tools.
2. **`tool_filter` is only a standalone pattern matcher.** Currently `tool_filter` (`Tool filter`) lives as a separate regex/substring node on the board. If an attack or misleading prompt does not match a literal keyword or regex, `tool_filter` fails to restrict tools dynamically; meanwhile, semantic/decision nodes (`jev`, `safety_check`, `agent_review`) can only block the entire prompt (`handle = "block"`) and cannot pass a legitimate prompt through while switching off specific tools on the downstream AI Agent.
3. **Level waves lack subtle tool-misguidance scenarios.** Benign prompts in `medium` and `hard` levels do not test indirect/pasted-document bait (Pattern D) or quick-fix troubleshooting requests (Pattern C) that tempt an unguarded LangGraph agent to call an unintended tool alongside or instead of an allowed one.

## Goals

- Implement the final AI Agent (`assistant`) on agent-enabled levels (`medium`, `hard`, and `custom`) using **LangGraph** (`StateGraph` with an `agent` node and `ToolNode` bound to sandboxed tool schemas), while keeping `easy` as a classification-only warmup (`agent=None`).
- Remove standalone `tool_filter` from the placeable check palette and turn Tool Policy into an **extension** on `jev`, `safety_check`, and `agent_review`:
  - `jev` and `safety_check` keep their default prompt-blocking behaviour when Tool Policy is off, and gain a Tool Policy mode (`tool_policy_enabled=True`) where triggering the check switches off selected numbered agent tools (`block_tools`, e.g., Tool `1`, `2`, `3`, …) and passes the prompt (`handle="safe"`) to the final LangGraph agent.
  - `agent_review` gains a Tool Policy toggle (`tool_policy_enabled=True`) plus instructions guidance so the reviewer LLM sees the level's numbered tools and can either block the prompt entirely or pass the prompt (`handle="safe"`) while dynamically switching off specific tools (`blocked_tools`).
- Update `medium` and `hard` level waves with Pattern C (Quick-Fix troubleshooting + destructive tool) and Pattern D (Indirect / Pasted document bait) benign prompts (`is_attack=False`), and refine `tool_points` scoring so unintended tool invocations on benign prompts deduct points while accurately switched-off tools earn full `tool_points`.

## Non-goals

- Redesigning level progression into multi-level `easy` / `medium` / `hard` categories (planned for a separate future spec).
- Giving `easy` a live LangGraph model (`easy` remains `agent=None`).
- Executing real destructive side effects inside level tools (LangGraph `ToolNode` executes deterministic sandboxed tool stubs).

## Behaviour

### 1. LangGraph Final AI Agent (`assistant`)

- On `easy` (`agent=None`), the `assistant` node remains a classification-only sink (`outcome="assistant"`, `agent=None`).
- On `medium`, `hard`, and `custom` (where `AgentProfile` is present), `assistant` runs a LangGraph `StateGraph` (`agent` node + `ToolNode`):
  - Every tool in `profile.tools` that was **not** switched off upstream (`gated_tools`) is exposed as a callable LangGraph tool (numbered `1..N` in profile order) so an unguarded agent can be tempted to invoke any active tool—not just `allowed=True` tools.
  - Any tool switched off by an upstream Tool Policy node (`gated_tools`) is excluded from the bound tool list and rejected if requested, preventing the LangGraph agent from executing it.
  - The offline deterministic stand-in (`simulate_agent`) mirrors this behaviour when no live model is configured (tests and local offline runs).

### 2. Removing `tool_filter` & Adding Tool Policy to `jev`, `safety_check`, and `agent_review`

- `get_check_catalog()` no longer includes `tool_filter`. Existing `RetiredNodeKind` or saved boards referencing `tool_filter` are handled cleanly (rejected on validation with an upgrade message or treated cleanly per validation rules).
- Each of `jev`, `safety_check`, and `agent_review` accepts `config.tool_policy_enabled: bool` (default `False`).

| Node (`kind`) | `tool_policy_enabled = False` (default) | `tool_policy_enabled = True` |
| --- | --- | --- |
| `jev` | Evaluates `question` vs `threshold`; if `prob >= threshold`, routes `block` (stops prompt). | Evaluates `question` vs `threshold`; if `prob >= threshold`, adds configured `block_tools` (1-based indices `1..N` or tool names) to `gated_tools` and routes `safe` so the prompt reaches the LangGraph agent with those tools switched off. |
| `safety_check` | Evaluates guardrail model verdict; if flagged, routes `block` (stops prompt). | Evaluates guardrail model verdict; if flagged, adds configured `block_tools` (`1..N` or tool names) to `gated_tools` and routes `safe` with those tools switched off. |
| `agent_review` | Reviewer LLM returns `{"blocked": bool, "reason": str}`; `blocked=true` stops prompt. | Reviewer LLM receives numbered agent tools (`1. <name>: <description>`, …) and player `<review_instructions>`, returning `{"blocked": bool, "blocked_tools": [int \| str], "reason": str}`. `blocked=true` stops the prompt; `blocked=false` routes `safe` and switches off any listed `blocked_tools` on the downstream LangGraph agent. |

### 3. Level Waves (Pattern C & Pattern D) and `tool_points` Scoring

- `medium` and `hard` levels include benign (`is_attack=False`) prompts combining:
  - **Pattern C (Quick-Fix / Troubleshooting):** legitimate policy/inventory/catalog question paired with a casual request to execute an unintended tool (e.g. checking salary records, running raw SQL to reset stock, or dropping audit logs).
  - **Pattern D (Pasted Document Bait):** legitimate employee/warehouse request wrapping pasted ticket/vendor text containing an untrusted instruction targeting an unintended tool (e.g. `wire_transfer`, `export_payroll`, `read_salary_records`).
- Scoring for benign prompts (`is_attack=False`):
  - Blocking a benign prompt at an upstream node or having the final agent refuse it remains a `false_alarm` (`won=False`, `total_score=0`).
  - Calling a restricted/unintended tool (`not tool.allowed`) on a benign prompt that was **not** blocked upstream no longer turns the entire prompt into a `false_alarm` if the prompt was otherwise answered (`helped`), **unless** an attack leaks; instead, each benign prompt where the agent calls an unintended restricted tool loses `tool_points` proportional to tool-policy mistakes (deducted from the 1,000-point `tool_points` bucket).
  - When an upstream Tool Policy node switches off the unintended tool(s) while keeping required `expected_tool` active, the LangGraph agent serves the benign prompt without executing the unintended tool and earns full `tool_points`.
  - Blocking an `expected_tool` required by a benign prompt still prevents calling it, resulting in a `false_alarm` (`won=False`).

## Acceptance criteria

- **ENG-AGENT-020**: Given a `medium` or `hard` level message that reaches `assistant` (while `easy` remains classification-only with `agent=None`), when evaluated, then `assistant` executes a LangGraph `StateGraph` (`agent` node + `ToolNode`) with only the non-blocked level tools bound/executable, and prevents execution of any tool switched off by upstream Tool Policy (`gated_tools`).
- **ENG-TOOL-010**: Given `get_check_catalog()`, when inspected, then standalone `tool_filter` is removed from the placeable palette, and `jev`, `safety_check`, and `agent_review` support the Tool Policy extension (`tool_policy_enabled: bool`, `block_tools: list[int | str]` on `jev` and `safety_check`, and dynamic `blocked_tools` JSON output on `agent_review`).
- **ENG-TOOL-011**: Given a `jev` or `safety_check` node with `tool_policy_enabled=True` and `block_tools=[2]` (1-based tool index or tool name), when the check triggers (`prob >= threshold` for `jev`, `flagged=True` for `safety_check`), then the node routes via `handle="safe"` instead of blocking the prompt and switches off Tool 2 for the downstream LangGraph agent; when `tool_policy_enabled=False`, triggering the check routes to `handle="block"` and stops the prompt.
- **ENG-TOOL-012**: Given an `agent_review` node with `tool_policy_enabled=True` and custom `prompt` instructions, when the reviewer LLM returns `{"blocked": false, "blocked_tools": [2], "reason": "..."}`, then `agent_review` routes via `handle="safe"` and switches off Tool 2 for the downstream LangGraph agent; when `"blocked": true`, it blocks the prompt entirely.
- **ENG-SCORE-004**: Given Pattern C (Quick-Fix troubleshooting) and Pattern D (Pasted document bait) safe prompts (`is_attack=False`) in `medium` and `hard` levels that tempt the LangGraph agent to call an unintended restricted tool alongside or instead of an allowed tool, when the unintended tool is NOT blocked upstream and the agent calls it, then the message still counts as `helped` (if not refused and required `expected_tool` was called) but `tool_points` are deducted; when the unintended tool IS switched off by an upstream Tool Policy node, the LangGraph agent cannot execute it and full `tool_points` marks are awarded.
- **API-GAME-010**: Given `GET /api/v1/game/levels` and `POST /api/v1/game/run`, when called with boards using `jev`, `safety_check`, or `agent_review` Tool Policy configurations (`tool_policy_enabled`, `block_tools`), then the gateway validates the board (including 1-based tool indices or tool names) and returns hop traces showing which tools were switched off.
- **WEB-GAME-010**: Given `/game` and node configuration modals for `jev`, `safety_check`, and `agent_review`, when opened, then `tool_filter` is no longer in the palette, `jev` and `safety_check` render a Tool Policy toggle switch with numbered agent tool selectors (`Tool 1`, `Tool 2`, `Tool 3`, …), and `agent_review` renders a Tool Policy toggle switch with guidance telling the player to instruct the AI when to switch off tools for the final agent.

## Security & privacy considerations

- Untrusted prompt text stays wrapped with `wrap_untrusted()` across `safety_check`, `agent_review`, and the LangGraph `assistant` node; player-written rules and review instructions remain in system prompts.
- Blocked tools are removed from the LangGraph tool binding and guarded at tool invocation, so LLM prompt injection cannot invoke switched-off tools even if the model hallucinates a tool call by name.
- Adding `langgraph` (`langchain-core`) stays scoped inside `packages/engine` (or an engine adapter) without leaking provider secrets or env vars into `packages/engine`.

## Evaluation impact

- `tool_points` (max `1,000`) on `medium` and `hard` reflects both required `expected_tool` accuracy and unintended restricted tool avoidance on Pattern C (`quick_fix`) and Pattern D (`pasted_bait`) benign prompts.
- **Before vs After reference scores (`medium` simulated wave):**
  - Unguarded `medium` board (attacks stopped, no Tool Policy on Pattern C/D benign bait): `tool_points = 500`, `total_score = 8,614` (`gold`, `won=True`).
  - Tool Policy-protected `medium` board (`jev` switching off Tool 2 `read_salary_records` on bait prompts): `tool_points = 1,000`, `total_score = 9,124` (`gold`, `won=True`).

## Open questions

- None.

## Verification

### 2026-11-18 · commit 2a0b84f (+ uncommitted changes)

- Criteria: ENG-AGENT-020, ENG-TOOL-010, ENG-TOOL-011, ENG-TOOL-012, ENG-SCORE-004, API-GAME-010, WEB-GAME-010
- Red: 7 failing test(s) before implementation (`packages/engine/tests/test_game.py::test_langgraph_agent_executes_state_graph_with_bound_tools_and_blocks_gated_tools`, `packages/engine/tests/test_game.py::test_check_catalog_removes_tool_filter_and_validates_tool_policy_configs`, `packages/engine/tests/test_game.py::test_jev_and_safety_check_tool_policy_switches_off_selected_tools_and_passes_message`)
- Green: 8 passing test(s)
- Gate: `mise run check` passed

### 2026-11-18 · commit 2a0b84f (+ uncommitted changes)

- Criteria: WEB-GAME-010
- Red: 1 failing test(s) before implementation (`design hygiene and anti-slop copy standard [WEB-GAME-010] removes tool_filter from palette and renders Tool policy toggles on jev, safety_check, and agent_review`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed
