# 0050 — Fair scoring and the scored run

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-26
- **Related:** [audit.md](audit.md) (evidence and full design), [0051](../0051-campaign-levels-v2/spec.md), [0021](../0021-game-level-tiers/spec.md), [0029](../0029-strict-win-lose-and-tool-config/spec.md), [0039](../0039-campaign-levels-and-difficulty-leaderboard/spec.md), [0044](../0044-leaderboard-read-scaling/spec.md)

## Problem

Scores do not measure skill ([audit.md](audit.md), F1 to F9). The wave is fixed and visible, so one lazy board wins
21 of the 22 levels that permit it. Latency is a server clock. Protection gives no points. One error gives 0, and the
same board can lose and then score 9,073 on the same level.

## Goals

- The same board gets the same score.
- Every run is a scored attempt, as in a level of a slingshot game. There is no practice run and no single-message test on campaign levels.
- A player cannot win by memorising the prompts.
- A loss shows progress, and a cleared board always scores more.
- A board with agent rules and no tools is permitted.

## Non-goals

- New level content and the agent prompt (0051).
- Daily challenges, percentiles and multiplayer.
- The custom sandbox score. It keeps its present rules.

## Behaviour

### One scored run

Each `Run wave` is a scored attempt. The best attempt is kept.

| | Value |
| --- | --- |
| Prompts | 24 prompts (12 attacks, 12 normal), hidden. The level briefing shows the families and one example of each |
| Shown after the run | For each prompt: its family, the result and the node that stopped it. Never the text, the agent reply or a free-text detail |
| Leaderboard | The best cleared attempt of each level |
| Daily runs | 50 paid, 5 free. Anonymous players get 1 run and record no score |

- A click on a result cell opens a list of its prompts. Each row shows the prompt number, the family and the node that stopped it. It shows no prompt text and no badge.
- The `Test a message` input is removed from campaign levels. The custom sandbox (0022) keeps it, because it uses the player's own key.
- Prompt text stays hidden because a visible wave lets an exact-text pattern clear any level (audit.md, F1).

### Limits stop the run (auto-defeat)

Each level has a latency limit for each prompt and a cost budget for the wave. Both use list prices, so a board
gets the same result each time.

| Event | Result |
| --- | --- |
| The list latency of one prompt's path is more than the limit | The run stops at that prompt: `Time limit exceeded` |
| The list cost of the wave so far is more than the budget | The run stops at that prompt: `Budget exceeded` |

- After a stop, no more prompts run and no model is called. The score is 0, and the attempt counts.
- The result names the prompt number, the path with the latency of each node, and the node that went over.
- The agent's own latency is not in the limit. Its cost is in the budget.
- Every level has both limits, and each limit binds (0051, ENG-LADDER-007).

### Spend protection

The pass earns about $0.15 a day after fees. The provider cost of one wave is from $0.0003 (one Jev node) to $0.37
(six LLM reviews with thinking). Counts alone do not protect the money, so there are three controls:

| Control | Value |
| --- | --- |
| Daily counts | Runs 50, training 20 (paid). Free: runs 5, training 3 |
| Daily provider budget for each player | $0.10 paid, $0.02 free. At the budget, runs stop until the next UTC day |
| Board size | At most 8 check nodes on any level, and at most 2 model-based nodes (`jev`, `safety_check`, `llm_review`) |

The list price of a model node with thinking is $0.006, so the level budget also limits thinking.

### Score

| Result | Score |
| --- | --- |
| Not cleared | `min(4999, round(4999 x A/At x N/Nt))` |
| Cleared | `round(5000 + 2500 Q + 1500 E + 1000 S)` |

- `A` attacks stopped of `At`; `N` normal prompts helped of `Nt`.
- Cleared: `A` and `N` are at or above the level floors, no critical leak, all limits kept.
- `Q = ((A+N) - (Af+Nf)) / ((At+Nt) - (Af+Nf))`, and 1 when the divisor is 0.
- `E` is the mean of latency and cost: `clamp((cap - used) / (cap - par), 0, 1)`.
- `S = clamp((node cap - nodes) / (node cap - par nodes), 0, 1)`, and 1 when the two are equal.
- Latency and cost are the sum of the catalogue list prices on each prompt's path, plus the list price of the tokens of the agent rules. Wall-clock time and the agent's own output are shown but give no points.
- Medals: bronze when cleared, silver from 8,000, gold from 9,250. Gold needs `Q` of 0.7 or more.
- Stars: one for cleared, one for gold, one for mastery. Mastery gives no points.

### The agent and repeatability

- A mixed request is helped when the expected tool ran and no forbidden tool ran, also if the reply says it refused a part.
- The agent result is stored by level version, model, prompt, switched-off tools and normalised rules. The same board reuses it. The canary of a wave is fixed for each level version and is never shown.
- A model failure records nothing and does not use a run.

### Boards

- A wire from Input to the final node is permitted.
- The tool filter never blocks a prompt because it contains a tool name. It only switches tools off, or blocks on a player's pattern.

## Acceptance criteria

- **ENG-FAIR-001**: Given any `A`, `N` and level floors, when a wave is scored, then a board that is not cleared scores at most 4,999, a cleared board scores 5,000 to 10,000, and block-all and allow-all score 0.
- **ENG-FAIR-002**: Given two cleared boards that differ only in `A + N`, then the larger total scores more; given `Q` less than 0.7, then no gold medal is possible.
- **ENG-FAIR-003**: Given the same board and agent replies with different wall-clock times, then score, medal and limits are equal.
- **ENG-FAIR-004**: Given a longer rule text on a board, then the list cost is higher and the score is not higher.
- **ENG-FAIR-005**: Given one critical leak or one broken limit, then the board is not cleared, whatever `A` and `N` are.
- **ENG-FAIR-006**: Given a mixed request with the expected tool run, no forbidden tool run and `refused: true`, then it is helped; given no expected tool run, then it is a false alarm.
- **ENG-FAIR-007**: Given Input wired to the final node, then the board is valid, and an allow-all board scores 0 on a wave where no attack is stopped.
- **ENG-FAIR-009**: Given a prompt whose path list latency is more than the level limit, then the run stops at that prompt, later prompts are not evaluated, no model is called for them, the score is 0, and the result names the prompt, the path and the node.
- **ENG-FAIR-010**: Given a wave whose list cost passes the level budget, then the run stops at that prompt with `Budget exceeded` and the same results as ENG-FAIR-009.
- **ENG-FAIR-011**: Given a board with more than 8 check nodes, or more than 2 model-based nodes, then it is rejected before any prompt runs.
- **API-FAIR-007**: Given a player whose provider cost today reached the daily budget, then a run returns `429` before any model is called, and the reply says when it resets.
- **API-FAIR-008**: Given the daily counts in the table, then each limit returns `429` at its count, and a stopped run (ENG-FAIR-009) counts.
- **ENG-FAIR-008**: Given a tool filter that switches off `increase_credit_limit` and a normal prompt that contains that word, then the prompt reaches the agent with the tool off.
- **API-FAIR-001**: Given a campaign run, then the response has no prompt text, agent reply or free-text detail of a prompt, in any field.
- **API-FAIR-002**: Given a campaign run with a single custom message, then the response is `422` and no model is called; the custom sandbox still accepts one.
- **API-FAIR-003**: Given the same board run twice, then the agent model is called only for the first, and the two scores are equal.
- **API-FAIR-004**: Given a model failure, then no run is used and no score is recorded; given a lower score than the best attempt, then the best attempt stays.
- **API-FAIR-005**: Given a not-cleared run, then it does not change the leaderboard; given equal totals, then more mastery stars rank first, then the earlier date.
- **API-FAIR-006**: Given the version 4 migration, then all scores of version 3 are deleted, and the leaderboard and progress start empty.
- **WEB-FAIR-001**: Given a campaign level, then the game page has no `Test a message` input and shows the runs left today; given the custom sandbox, then the input stays.
- **WEB-FAIR-003**: Given a stopped run, then the present result modal shows `Time limit exceeded` or `Budget exceeded`, the prompt number, the path with each node's latency or cost, and the node that went over.
- **WEB-FAIR-004**: Given a click on a result cell, then each row of the list shows the prompt number, the family name and the stopping node with its score when it has one, and no prompt text and no badge.
- **WEB-FAIR-002**: Given a run result, then the present result modal shows the score and only the score parts that count on that level, with the result for each family; a part that does not count on the level is not shown.

## Security & privacy considerations

- Wave prompts are server secrets. They are not in the level catalogue, the contract, logs or saved boards. A leak is corrected by a new level version, which starts a new store key.
- A player can learn from pass and fail counts. The daily run limit and the family-only report keep this slow.
- The store holds no player text except the hash of normalised rules.

## Evaluation impact

Before, measured on 2026-11-26 with the old score: the memoriser board won 21 of 22 levels that permit it, one
general regex board won 17, and live Hard won 0 of 24.

After, measured on 2026-11-26 with the new score on the present 23 levels (offline agent): the memoriser board
clears 22 of 22 (gold on each, 9,667 to 9,857), and the general regex board clears 11. The score alone does not stop
lazy boards on the present content. Two parts of this spec stop them in play: the run response and the level
catalogue no longer send prompt text, so a player cannot build the memoriser; and 0051 replaces the content. The
calibration report of 0051 records the after values for the new levels. The formula was checked for all `A` and `N`
with the floors of all 19 levels.

Generic one-node boards, measured 2026-11-26 on today's levels: Jev with a general question clears 15 of 23 levels
alone. On new-style prompts it stops 1 of 20 attacks; with a question written for the level it stops 17 to 19 of 20.

## Replaced criteria

These criteria in Implemented specs change. During the cycle, each one gets the text `Replaced by <new ID> (0050).`, and its test is changed to test the new behaviour and also carries the new ID.

| Old | Spec | New | What changes |
| --- | --- | --- | --- |
| ENG-SCORE-001, ENG-SCORE-002 | 0029 | ENG-FAIR-001, ENG-FAIR-005 | A campaign loss scores up to 4,999, not 0. `score_wave` keeps the old rule for the custom sandbox |
| ENG-SCORE-003 | 0029 | ENG-FAIR-001, ENG-FAIR-002 | New score parts and medal bars |
| ENG-SCORE-004 | 0037 | ENG-FAIR-001 | Tool points stay only in the custom sandbox score |
| ENG-LEVEL-003 | 0021 | ENG-FAIR-001 | Easy uses the same formula as all levels |
| ENG-GAME-007 | 0016 | ENG-FAIR-007 | Input may wire straight to the final node |
| ENG-LEVEL-007 | 0021 | ENG-FAIR-007 | A board with no check node is permitted. The label rule stays |
| ENG-GAME-003, ENG-TOOL-005 | 0016, 0029 | ENG-FAIR-008 | A switched-off tool does not block the prompt that names it |
| ENG-CAMP-002 | 0039 | ENG-FAIR-009, ENG-FAIR-010, ENG-FAIR-011 | Limits stop the run at the prompt, not after the wave. The node cap is 8 |
| API-LEVEL-004, API-CAMP-002 | 0021, 0039 | API-FAIR-006 | Score version 4 replaces version 3 |
| API-LEVEL-003 | 0021 | API-FAIR-002, API-FAIR-008 | Model-free Easy runs still use no run count and no budget. There are no single tests on campaign levels |
| API-GAME-003, API-GAME-007, API-AGENT-001, API-SPEND-009 | 0016, 0020, 0042 | API-FAIR-002, API-FAIR-008 | No single tests on campaign levels; paid runs are 50 a day. The 1,000-character cap applies to the custom sandbox |
| API-TRAIN-014 | 0045 | API-FAIR-008 | Paid training is 20 a day |
| API-LBOARD-013, API-LBOARD-029 | 0044 | API-FAIR-005 | Ties sort by mastery stars, then the earlier date, not by latency. The chunk rules of API-LBOARD-032 to 034 stay |
| WEB-GAME-002 | 0029 | WEB-FAIR-001 | No custom test message on campaign levels |
| WEB-AGENT-015 | 0020 | WEB-FAIR-001 | The label reads `42 / 50 runs left today` |
| WEB-AGENT-004, WEB-LEVEL-001 | 0020, 0021 | WEB-FAIR-002 | The score parts are those of the spec 0050 formula |
| WEB-AGENT-022 | 0020 | WEB-FAIR-004 | The cell list shows the family, not the text |

The level count (ENG-CAMP-001, API-CAMP-001, WEB-CAMP-004) changes in 0051.

## Open questions

Decided on 2026-11-26: scores reset with no seasons; no practice run and no single-message test on campaign levels; runs are 50 a day paid and 5 free; the present result modal stays, with no new UI design.

None.

## Verification

### 2026-11-26 · commit 7d6a8d9 (+ uncommitted changes)

- Criteria: ENG-FAIR-009, ENG-FAIR-010, ENG-FAIR-011, API-FAIR-001, API-FAIR-002, API-FAIR-003, API-FAIR-004, API-FAIR-005, API-FAIR-006, API-FAIR-007, API-FAIR-008, WEB-FAIR-001, WEB-FAIR-002, WEB-FAIR-003, WEB-FAIR-004
- Red: 15 failing test(s) before implementation (`packages/engine/tests/test_fair_limits.py::test_a_prompt_over_the_time_limit_stops_the_run`, `packages/engine/tests/test_fair_limits.py::test_a_wave_over_the_cost_budget_stops_at_that_prompt`, `packages/engine/tests/test_fair_limits.py::test_boards_over_the_node_caps_are_rejected`)
- Green: 16 passing test(s)
- Gate: `mise run check` passed

### 2026-11-26 · commit 7d6a8d9 (+ uncommitted changes)

- Criteria: WEB-FAIR-002, WEB-FAIR-004
- Red: 2 failing test(s) before implementation (`Scored runs on the game page (spec 0050) [WEB-FAIR-002] shows only the score parts that count on the level`, `Scored runs on the game page (spec 0050) [WEB-FAIR-004] lists the prompt number, family and stopping node, with no text or badge`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed
