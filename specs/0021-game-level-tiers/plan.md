# 0021 — Game level tiers: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

- **Engine** (`shield_engine/game/`): `GameLevel.agent` becomes
  `AgentProfile | None` and gains `agent_tier: AgentTier | None` and
  `final_node_label`. `run_wave` and `evaluate_message` take
  `agents: Mapping[AgentTier, UsageChatModel]` instead of one `agent`, and
  pick the level's tier. When `level.agent is None`, reaching the final node
  ends the trace with no agent run. `score_wave` gains a `classify_only` flag
  that switches to the Easy weights. `simulate_agent` takes the tier.
  `parse_agent_output` strips a code fence and reads the first JSON object.
- **Gateway:** `Settings` gains `GAME_MODEL_STANDARD` and `GAME_MODEL_BUDGET`.
  `Container.game_agents: dict[AgentTier, UsageChatModel]` replaces
  `game_agent`. The router skips `check_run` and `consume_run` on Easy, and
  records Easy scores with `agent_mode == "none"`.
- **Web:** the starter board takes the level's `final_node_label`. The node
  modal branches on `levelAgent === null` for Easy. `scoreBreakdown` takes
  the level and drops tool and token rows on Easy.

## Interfaces

```python
AgentTier = Literal["standard", "budget"]
AgentMode = Literal["live", "simulated", "none"]

async def run_wave(board, *, level_id, classifier=None,
                   agents: Mapping[AgentTier, UsageChatModel] | None = None,
                   canary_factory=new_canary) -> WaveResult: ...
def score_wave(..., classify_only: bool = False) -> WaveScore: ...
def simulate_agent(*, tier: AgentTier, ...) -> AgentRun: ...
```

Breaking: `run_wave(agent=...)` becomes `run_wave(agents=...)` (engine public
API), and `GameLevelSchema.agent` becomes nullable (HTTP contract).

## Boundaries check

- [ ] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [ ] Model names live only in gateway settings, never in the engine
- [ ] `apps/web` still talks to the backend only through the published OpenAPI contract
- [ ] New settings are documented in `docs/reference/configuration.md`

## Alternatives considered

| Option | Why not |
| --- | --- |
| A new `help_desk` node kind for Easy | Changes board validation and every saved board for no gain; the label is enough |
| Hard-coding model names per level in the engine | The engine must not know providers; tiers keep it pure |

## Risks and rollback

- The budget model may be retired by the provider. The tier is configuration,
  so swapping the model is a settings change.
- Rollback: revert the spec's commit; boards are unchanged, so saved boards
  keep working.
