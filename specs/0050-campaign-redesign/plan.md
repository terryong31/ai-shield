# 0050 — Campaign redesign: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

Four slices, each one SDD cycle, in this order. Each slice leaves `mise run check` green.

1. **Score (engine).** Replace `score_wave` and `_AGENT_WEIGHTS` in `shield_engine/game/__init__.py` with the
   formula of the spec. Latency and cost come from the catalogue list prices on each prompt's path, not from
   `perf_counter`. A new pure function computes `Q`, `E` and `S`. IDs: ENG-FAIR-001 to 008.
2. **Limits and board size (engine).** `run_wave` checks the list latency and the running list cost before each
   prompt and stops with `Time limit exceeded` or `Budget exceeded`. `validate_board_for_level` adds the caps of
   8 check nodes and 2 model nodes. IDs: ENG-FAIR-009 to 011.
3. **Gateway.** `routers/game.py` removes prompt text, replies and details from campaign run results, rejects a
   single custom message on campaign levels, adds the agent result store, and keeps the best attempt.
   `services/players.py` sets the new daily counts and the daily provider budget. A migration deletes version 3
   scores. Tie order moves to mastery stars, then date. IDs: API-FAIR-001 to 008.
4. **Web.** `game.vue` removes `Test a message` on campaign levels and shows the runs left. The present result
   modals stay. `scoreBreakdown` returns only the parts that count on the level. The cell list shows number,
   family and stopping node. IDs: WEB-FAIR-001 to 004.

Level content stays as it is until 0051. Each present level gets temporary floors equal to its full wave, so the
present behaviour (a leak loses) stays until 0051 sets the real floors.

## Interfaces

Breaking: `WaveScore` fields, the run response (no prompt text on campaign levels) and the contract. Run
`mise run contract` in slice 3.

```python
def score_wave(traces: Sequence[MessageTrace], level: GameLevel, board: BoardGraph) -> WaveScore: ...
def path_list_latency_ms(trace: MessageTrace) -> float: ...
def path_list_cost_usd(trace: MessageTrace) -> float: ...
class RunStopped(Exception): reason: Literal["time_limit", "budget"]; prompt_index: int; node_id: str
```

## Boundaries check

- [ ] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [ ] The provider budget lives in the gateway; the engine only reports list cost
- [ ] Ranked prompt text never leaves the gateway in a campaign response
