# 0020 — Game AI Agent: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

**Engine (`shield_engine/game`).** Drop `blocked` from the anchor kinds and
make an unwired output end the trace as `blocked`. Add an `AgentProfile`
to `GameLevel` and an `expected_tool` to `LevelMessage`. Add an `agent.py`
module that builds the prompt (objective, tools, `<player_rules>`, canary,
`wrap_untrusted(message)`), calls the model, parses the JSON reply and judges
it. `run_wave` and `evaluate_message` take an optional `agent` port and a
`canary_factory`, so tests can be deterministic. `score_wave` gains the new
components. A `SimulatedAgent` in the engine handles the no-model case: it
keyword-matches rules against known attack phrases.

**Gateway (`shield_api`).** `container.py` wires a `UsageChatModel` from the
first configured provider (Gemini, then Groq) into the game router. The
router checks quota before running, maps provider errors to `503` without
consuming quota, and records scores only for live runs with `score_version=2`.
`services/players.py` replaces the free-only limits with a per-tier table. It
counts anonymous sessions too.

**Web (`apps/web`).** Update `createStarterBoard` (no `blocked`, label
`AI Agent`), add the rules editor and agent run list to the node modal,
redesign `GameNode.vue`, add the anonymous sign-in prompt, and show the new
score breakdown.

## Interfaces

```python
# shield_engine/ports.py (additive)
@dataclass(frozen=True, slots=True)
class ChatCompletion:
    text: str
    input_tokens: int | None
    output_tokens: int | None

class UsageChatModel(Protocol):
    async def complete_with_usage(
        self, messages: Sequence[ChatMessage], *, temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatCompletion: ...

# shield_engine/game (changed)
NodeKind = Literal[..., "assistant"]          # "blocked" removed (BREAKING)
@dataclass(frozen=True)
class AgentTool: name: str; description: str; allowed: bool
@dataclass(frozen=True)
class AgentProfile: objective: str; tools: tuple[AgentTool, ...]; token_budget: int
@dataclass(frozen=True)
class AgentRun:
    reply: str; tool_calls: tuple[str, ...]; refused: bool
    verdict: Literal["leaked", "protected", "helped", "false_alarm"]
    input_tokens: int; output_tokens: int; estimated_tokens: bool; latency_ms: float
# MessageTrace gains `agent: AgentRun | None`
# WaveScore gains helpfulness_points, tool_points, token_points, total_tokens
# WaveResult gains agent_mode: Literal["live", "simulated"]
async def run_wave(board, *, level_id, classifier=None, agent: UsageChatModel | None = None,
                   canary_factory: Callable[[], str] = ...) -> WaveResult
```

HTTP: `GameLevelSchema` gains `agent`. `MessageTraceSchema` gains `agent`.
`WaveScoreSchema` gains the new components. `GameRunResponse` gains
`agent_mode`. `NodeKind` loses `blocked`. Run `mise run contract` (contract
change, approved through this spec).

## Boundaries check

- [ ] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [ ] Provider SDKs stay in `shield_engine/adapters/` and `shield_api/demo/`, and each implements `complete_with_usage`
- [ ] Every LLM prompt built in the engine wraps player messages with `wrap_untrusted()`
- [ ] `apps/web` still talks to the backend only through the published OpenAPI contract
- [ ] New settings (none expected) documented in `docs/reference/configuration.md`
- [ ] `players` table changes go through `mise run db:migration` and are mirrored in SQLite

## Alternatives considered

| Option | Why not |
| --- | --- |
| Keep a `Blocked` node but make it optional | Two ways to express the same outcome. The player asked for unreached prompts to count as blocked. |
| Simulated agent only | Rules would only work if they contained the right keywords, which defeats the point of writing rules. |
| Estimate tokens only | Inaccurate for scoring. Provider usage is available from Groq and Gemini. |
| Judge leaks with a second LLM | Adds cost and nondeterminism. Canary and forbidden-tool checks are exact. |

## Risks and rollback

- **LLM cost.** At most about 12 agent calls per wave, with 300-token replies, under per-tier daily caps. To roll back, set no provider key: the game falls back to the simulated agent and stops recording scores.
- **Breaking contract.** Removing `blocked` breaks older clients. Web and API ship together from this repository.
- **Nondeterministic live scores.** These are mitigated by temperature `0`. Tests use fakes only.
