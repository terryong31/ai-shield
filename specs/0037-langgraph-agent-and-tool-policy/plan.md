# 0037 — LangGraph AI Agent and Tool Policy extension: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

1. **Engine LangGraph Final Agent (`packages/engine/pyproject.toml`, `packages/engine/src/shield_engine/game/agent.py`)**:
   - Add `langgraph` (and `langchain-core` base chat model bridge) to `packages/engine/pyproject.toml`.
   - Build a bridge wrapping `UsageChatModel` into a `langchain_core.language_models.chat_models.BaseChatModel` with `bind_tools(...)` support (using `UsageChatModel.complete_with_usage` so all existing adapters—Gemini, Groq, BYOK, and `ScriptedUsageChatModel` test doubles—work seamlessly with LangGraph without breaking `ports.py`).
   - Implement `StateGraph` (`agent` node + `ToolNode` + conditional `tools_condition` edge) inside `shield_engine/game/agent.py`. Each `AgentTool` in `AgentProfile.tools` (filtered to exclude `gated_tools`) is built as a sandboxed `@tool` returning deterministic mock data; tool calls made during graph execution are captured in `AgentRun.tool_calls` along with real token usage, latency, and cost.
   - Update `simulate_agent` to preserve deterministic offline simulation when `model is None`, including simulating Pattern C / Pattern D unintended tool temptations when those tools are not in `gated_tools`.

2. **Tool Policy Extension & Palette Update (`packages/engine/src/shield_engine/game/__init__.py`)**:
   - Remove `tool_filter` from `CHECK_CATALOG` (update `NodeKind` / `RetiredNodeKind` and `validate_board` so legacy `tool_filter` boards fail cleanly or migrate per validation rules).
   - Add `tool_policy_enabled: bool` and `block_tools: list[int | str]` validation in `validate_board` for `jev`, `safety_check`, and `agent_review` (validating 1-based tool indices `>= 1` and string tool names).
   - Update `evaluate_message`:
     - Pass `gated_tools` down into `run_live_agent` / `simulate_agent` so switched-off tools are excluded before the LangGraph agent runs.
     - In `jev` and `safety_check`: when triggered and `tool_policy_enabled=True`, resolve `block_tools` (1-based index into `profile.tools` or exact tool name), add them to `gated_tools`, set `handle="safe"`, and record the switched-off tools in `HopTrace.detail`. When `tool_policy_enabled=False`, route `handle="block"`.
     - In `agent_review`: when `tool_policy_enabled=True`, inject the numbered list of `profile.tools` (`1. <name>: <description>`, …) and Tool Policy instructions into the reviewer system prompt, parse `{"blocked": bool, "blocked_tools": [...], "reason": str}`, add resolved `blocked_tools` to `gated_tools`, and route `handle="safe"` unless `"blocked": true`.

3. **Level Waves & `tool_points` Scoring (`packages/engine/src/shield_engine/game/__init__.py`, `packages/engine/src/shield_engine/game/agent.py`)**:
   - Add Pattern C (Quick-Fix troubleshooting) and Pattern D (Pasted document bait) benign prompts (`is_attack=False`) to `LEVELS` for `medium` and `hard`.
   - Update `judge_agent` and `score_traces` / `score_wave` so that on benign prompts (`is_attack=False`), calling an unintended restricted tool (`not tool.allowed`) deducts points from `tool_points` rather than triggering a full `false_alarm` loss, whereas switching it off upstream via Tool Policy preserves full `tool_points`.

4. **API Gateway & Contract (`apps/api/src/shield_api/schemas.py`, `apps/api/src/shield_api/routers/game.py`)**:
   - Sync `NodeKind` / `RetiredNodeKind` updates from `shield_engine.game`, ensure `GET /api/v1/game/levels` and `POST /api/v1/game/run` expose updated check catalog and validate Tool Policy configs (`tool_policy_enabled`, `block_tools`), and run `mise run contract` to update `contracts/shield-api.openapi.json` and `apps/web/app/types/api.gen.ts`.

5. **Web Client (`apps/web/app/utils/gameBoard.ts`, `apps/web/app/pages/game.vue`)**:
   - Remove `tool_filter` from `toolKinds` and `NODE_CATALOG` in `apps/web/app/utils/gameBoard.ts` and `apps/web/app/pages/game.vue`.
   - In `apps/web/app/pages/game.vue` node settings modal:
     - On `jev` and `safety_check`: add a `<USwitch>` (`Tool policy: switch off agent tools instead of blocking prompt`) and a numbered tool selector (`1. <tool>`, `2. <tool>`, `3. <tool>`, …) bound to `config.block_tools`.
     - On `agent_review`: add a `<USwitch>` (`Allow switching off final agent tools`) with helper text advising the player to instruct the reviewer AI which numbered tools to turn off for the final agent.

## Interfaces

```python
# packages/engine/src/shield_engine/game/agent.py
async def run_live_agent(
    model: UsageChatModel,
    *,
    profile: AgentProfile,
    rules: Sequence[str],
    canary: str,
    message: str,
    is_attack: bool,
    expected_tool: str | None,
    gated_tools: frozenset[str] = frozenset(),
) -> AgentRun: ...

def simulate_agent(
    *,
    profile: AgentProfile,
    tier: AgentTier = "budget",
    rules: Sequence[str],
    canary: str,
    message: str,
    is_attack: bool,
    expected_tool: str | None,
    gated_tools: frozenset[str] = frozenset(),
) -> AgentRun: ...
```

```typescript
// Node config additions for jev, safety_check, and agent_review
interface ToolPolicyConfig {
  tool_policy_enabled?: boolean
  block_tools?: Array<number | string> // 1-based tool index or tool name (jev & safety_check)
}
```

## Boundaries check

- [ ] `packages/engine` still imports nothing from web frameworks, databases, or `shield_api`; it uses `langgraph` / `langchain-core` purely over `UsageChatModel`.
- [ ] `apps/web` still talks to the backend only through the published OpenAPI contract (`api.gen.ts` regenerated via `mise run contract`).
- [ ] New configuration and engine behaviour are documented in `docs/reference/engine-api.md` and `docs/reference/http-api.md`.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Keep custom single-turn JSON prompt in `agent.py` | Does not model real LangGraph `StateGraph` + `ToolNode` tool-binding behaviour that `ai-shield` is designed to defend. |
| Keep `tool_filter` as a separate regex node | Cannot interpret semantic intent or indirect bait prompts; folding Tool Policy into `jev`, `safety_check`, and `agent_review` lets players pair detection with selective tool restriction. |
| Hard-fail benign prompts as `false_alarm` whenever an unintended tool is called | User explicitly wants unintended tool calls on benign prompts to deduct `tool_points` (and award full marks when switched off upstream) rather than immediately zeroing the whole run as a false alarm. |

## Risks and rollback

- **Risk:** Small/budget live models may format tool calls variably through custom `UsageChatModel` adapters; bridging `UsageChatModel` cleanly into LangGraph's `BaseChatModel` with structured tool-call support (and deterministic parsing fallback) keeps Gemini, Groq, and test doubles working uniformly.
- **Risk:** Removing `tool_filter` may affect legacy saved boards; `RetiredNodeKind` validation gives players a clear message on how to migrate to Tool Policy on `jev` / `safety_check` / `agent_review`.
- **Rollback:** Spec 0037 has not altered any database schema; reverting the branch restores the previous `agent.py` and `tool_filter` implementation cleanly.
