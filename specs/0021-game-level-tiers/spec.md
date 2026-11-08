# 0021 — Game level tiers: classifier, modern agent, budget agent

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-08
- **Related:** [spec 0020](../0020-game-ai-agent/spec.md) (AI Agent, scoring, quotas), [spec 0022](../0022-game-custom-sandbox/spec.md) (custom sandbox), [plan.md](plan.md), [tasks.md](tasks.md)

## Problem

All three levels run the same AI Agent on the same model
(`Container.game_agent`, Gemini first, then Groq's `GROQ_CHAT_MODEL`). The
only thing that changes between levels is how sneaky the attacks are
(`_LEVELS` in `shield_engine/game/__init__.py`). That leaves two gaps:

- **Level one asks too much at once.** A new player has to learn routing,
  agent rules, tool use and token cost in one go, before they have learned
  the basic skill: tell a normal prompt from an injection.
- **The model is never the variable.** In production, companies often put a
  small or cheap model behind a support bot to save money, and those models
  follow injected instructions far more readily. The game never shows that
  the same defences hold differently depending on the model behind them.

## Goals

- **Level one (Easy) is classification only.** No LLM runs. The final node is
  a plain destination, `Help Desk`. A prompt that reaches it was let
  through; any other prompt was blocked. The score is about telling good
  prompts from bad ones.
- **Level two (Medium) runs a modern, capable model** as the AI Agent, as in
  spec 0020.
- **Level three (Hard) runs a small, low-cost model** as the AI Agent, the
  kind a company picks to save money. It is more easily injected, so the
  player's board and rules carry more of the defence.
- Each level says which kind of model it runs, so the player knows what they
  are defending.

## Non-goals

- The custom sandbox with player keys and datasets (spec 0022).
- Changing the attack messages of any level beyond what the table below lists.
- Changing the screening pipeline (`Shield`) or its benchmark.
- Running `safety_check` and `agent_review` against real models.

## Behaviour

### Levels

| Level | Final node | Model | Scored components |
| --- | --- | --- | --- |
| Easy (`easy`) | `Help Desk` (no LLM) | none | protection, helpfulness, speed, cost |
| Medium (`medium`) | `AI Agent` | `standard` tier: `GAME_MODEL_STANDARD` | as spec 0020 |
| Hard (`hard`) | `AI Agent` | `budget` tier: `GAME_MODEL_BUDGET` | as spec 0020 |

- The engine knows only a **model tier** per level (`None`, `"standard"`,
  `"budget"`). Which concrete model serves a tier is gateway configuration,
  never engine code.
- The node kind stays `assistant` on every level, so boards and validation do
  not change. Only its label and behaviour depend on the level.

### Level one: classification

- When a prompt reaches `Help Desk`, the trace outcome is `assistant` and
  `agent` is `null`. An attack that arrives counts as **let through**; a
  normal prompt that arrives counts as **served**.
- No canary, no tokens, no tool use. `total_tokens` is `0`.
- Score weights (total still 10,000):

  | Component | Points |
  | --- | --- |
  | Protection (attacks stopped / attacks) | 5,000 |
  | Helpfulness (normal prompts served / normal prompts), minus 300 per false alarm | 3,000 |
  | Speed | 1,000 |
  | Cost | 1,000 |
  | Leak penalty | −1,000 per attack let through |

  Tool use and tokens are reported as `0` points and left out of the
  breakdown. Medal thresholds are unchanged.
- A custom test on Easy scores the message as an attack, as today: it is
  protected unless it reaches `Help Desk`.
- The AI Agent rules editor is not shown on Easy. Rules sent in
  `config.rules` for Easy are ignored, not rejected.

### Level two and three: model tiers

- The gateway maps tiers to models:

  | Setting | Default | Used by |
  | --- | --- | --- |
  | `GAME_MODEL_STANDARD` | the configured Gemini model, else `GROQ_CHAT_MODEL` | Medium |
  | `GAME_MODEL_BUDGET` | `llama-3.1-8b-instant` on Groq | Hard |

- If a level's tier has no configured model, the run uses the offline
  simulated agent for that tier and the result has `agent_mode: "simulated"`
  (not recorded on the leaderboard, as in spec 0020).
- The **simulated** agent now differs by tier, so offline play keeps the
  difference:
  - `standard` resists a direct override (`ignore previous instructions`,
    `reveal`, `system prompt`) even with no player rules, and leaks only on
    encoded or indirect attacks the board did not stop, unless a defensive
    rule is set.
  - `budget` behaves as today: it leaks on every attack that reaches it,
    unless the player's rules include a defensive rule.
- The reply parser accepts the agent's JSON reply when it is wrapped in a
  Markdown code fence or followed by extra text, because small models often
  do this. A reply that still cannot be parsed counts as plain text with no
  tool calls, as today.

### Catalog and HTTP

- `GameLevelSchema` gains `agent_tier: "standard" | "budget" | null` and
  `final_node_label: str` (`"Help Desk"` or `"AI Agent"`).
- `GameLevelSchema.agent` becomes nullable (`null` on Easy).
- `GameRunResponse.agent_mode` gains `"none"` for Easy, where no agent runs.
  Easy runs with `agent_mode: "none"` **are** recorded on the leaderboard for
  signed-in players, because they need no model.

### Leaderboard

- Each score row carries `score_version`. Rows from before this spec are
  version `1`; rows recorded now are version `2`. The leaderboard lists only
  the current version, so old rows on a different scale are not ranked
  against new ones. Old rows stay in the database.

### Quotas

- Easy calls no model, so its runs cost nothing to serve. Easy runs and tests
  **do not count** toward the daily quotas of spec 0020, for any tier.
  Anonymous players are still shown the sign-in prompt before each run on
  every level.

### Web

- The starter board labels the final node from the level
  (`final_node_label`).
- On Easy, the final node's modal shows a `What this node does` section
  ("Every prompt that reaches the help desk is answered. Stop the
  injections before they get here.") and the `Last wave` summary, with no
  objective, tools or rules.
- On Medium and Hard, the AI Agent modal shows a `Model` section naming the
  tier: `Modern model` with "A current, capable model. It refuses many
  attacks by itself." or `Budget model` with "A small, low-cost model, the
  kind companies run to save money. It follows injected instructions more
  easily, so your board has to do more of the work."
- The level cards on `/` say which model each level defends: `No AI model`,
  `Modern AI model`, `Budget AI model`.
- The score breakdown leaves out `Tool use` and `Tokens` on Easy.

## Acceptance criteria

- **ENG-LEVEL-001**: Given the Easy level, when it is loaded, then `agent` is `None`, `agent_tier` is `None` and `final_node_label` is `"Help Desk"`; Medium has `agent_tier == "standard"` and Hard has `agent_tier == "budget"`, both with `final_node_label == "AI Agent"`.
- **ENG-LEVEL-002**: Given an Easy wave and a configured agent model, when it runs, then the model is never called, every trace has `agent is None`, `total_tokens == 0`, `agent_mode == "none"`, and an attack that reaches the final node counts as let through while a normal prompt that reaches it counts as served.
- **ENG-LEVEL-003**: Given an Easy wave, when it is scored, then protection is worth 5,000, helpfulness 3,000 (minus 300 per false alarm), speed 1,000 and cost 1,000, tool and token points are `0`, a board that stops every attack and serves every normal prompt at zero latency and cost scores 10,000, and each attack let through costs 1,000.
- **ENG-LEVEL-004**: Given Medium and Hard waves run by `run_wave` with a model per tier, when they run, then Medium calls only the `standard` model and Hard calls only the `budget` model.
- **ENG-LEVEL-005**: Given no model for a tier, when that level runs, then the simulated agent for that tier is used: with no player rules and an unfiltered board, the `standard` stand-in refuses a direct override attack while the `budget` stand-in leaks it, and both protect when a defensive rule is set.
- **ENG-LEVEL-006**: Given an agent reply that is valid JSON wrapped in a Markdown code fence, or followed by trailing text, when it is parsed, then its `reply`, `tool_calls` and `refused` fields are read; an unparseable reply still counts as plain text with no tool calls.
- **API-LEVEL-001**: Given `GET /game/levels`, when it returns, then each level has `agent_tier` and `final_node_label`, and Easy has `agent: null`.
- **API-LEVEL-002**: Given the gateway settings, when the container is built, then `GAME_MODEL_STANDARD` and `GAME_MODEL_BUDGET` pick the models for Medium and Hard, a run on each level uses its own tier's model, and a tier with no model runs simulated (`agent_mode: "simulated"`, not recorded).
- **API-LEVEL-003**: Given a signed-in or anonymous player, when they run Easy waves or tests, then those runs do not use up their daily quota, a signed-in player's Easy wave is recorded on the leaderboard with `agent_mode: "none"`, and Medium and Hard runs are still counted.
- **API-LEVEL-004**: Given leaderboard rows recorded before this spec, when scores are listed, then only rows with the current `score_version` (`2`) are returned; rows stored earlier keep `score_version = 1` in SQLite (added with a default on start-up, no data loss) and new rows are stored with `2`.
- **WEB-LEVEL-001**: Given `/game?level=easy`, when the board loads, then the final node is labelled `Help Desk`, its modal shows `What this node does` and `Last wave` but no objective, tools or rules editor, and the score breakdown leaves out `Tool use` and `Tokens`.
- **WEB-LEVEL-002**: Given `/game` on Medium or Hard, when the AI Agent modal opens, then it shows a `Model` section with `Modern model` or `Budget model` and its explanation, and the level cards on `/` say `No AI model`, `Modern AI model` or `Budget AI model`.
- **WEB-LEVEL-003**: Given the level cards on `/`, when they render, then they show no model label (`No AI model`, `Modern AI model`, `Budget AI model`); the model is named only in the AI Agent modal. (Narrows WEB-LEVEL-002 at the owner's request.)
- **WEB-LEVEL-004**: Given the AI Agent modal on Medium or Hard, when it opens, then it shows no `Model` section; the level's model tier is not shown to the player. (Narrows WEB-LEVEL-002 at the owner's request.)
- **ENG-LEVEL-007**: Given Medium, Hard or the custom sandbox, when the final node is labelled, then it is `Protected Agent` (Easy stays `Help Desk`), and a board with no tool between Input and the final node is rejected with `Place at least one tool node between Input and the final node.`
- **WEB-LEVEL-005**: Given the final node's settings modal on any level, when it opens, then the line under the title reads `Wire your last check here. Everything that arrives gets answered, so only let safe prompts through.`, and the agent's objective section is headed `System Instruction`. (Renames `AI Agent` at the owner's request.)

## Security & privacy considerations

- **No change to what enters an LLM.** Medium and Hard still wrap every
  message with `wrap_untrusted()` and use a per-run canary. Easy sends nothing
  to any model.
- **Uncounted Easy runs are cheap but not free.** They run the local
  classifier on the gateway's CPU. The existing request rate limits still
  apply. If abuse appears, add an Easy cap rather than counting it against
  the LLM quota.
- **The budget model is weaker by design.** It only ever sees the per-run
  canary, never real credentials, so a leak exposes nothing.

## Evaluation impact

None for the screening pipeline: `mise run eval` measures `Shield`, which
this spec does not touch.

| | n | precision | recall | f1 | fpr | abstain | p50 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Before | 40 | 1.000 | 0.550 | 0.710 | 0.000 | 0.375 | 0.13 ms |
| After | 40 | 1.000 | 0.550 | 0.710 | 0.000 | 0.375 | 0.13 ms |

## Open questions

Resolved by the owner on 2026-11-08:

1. Budget model: `llama-3.1-8b-instant` on Groq.
2. Old leaderboard rows: add `score_version` now (API-LEVEL-004).
3. Easy runs never count toward the daily quota.
4. Medium messages stay as they are for now.

## Verification

_Filled in by `mise run sdd:done`._

### 2026-11-08 · commit ce5746e (+ uncommitted changes)

- Criteria: ENG-LEVEL-001, ENG-LEVEL-002, ENG-LEVEL-003, ENG-LEVEL-004, ENG-LEVEL-005, ENG-LEVEL-006, API-LEVEL-001, API-LEVEL-002, API-LEVEL-003, API-LEVEL-004, WEB-LEVEL-001, WEB-LEVEL-002
- Red: 12 failing test(s) before implementation (`packages/engine/tests/test_game_levels.py::test_easy_has_no_agent_and_medium_and_hard_name_their_model_tier`, `packages/engine/tests/test_game_levels.py::test_easy_wave_never_calls_a_model_and_counts_arrivals`, `packages/engine/tests/test_game_levels.py::test_easy_scoring_weights_classification_only`)
- Green: 12 passing test(s)
- Gate: `mise run check` passed

### 2026-11-08 · commit ce5746e (+ uncommitted changes)

- Criteria: WEB-LEVEL-003
- Red: 1 failing test(s) before implementation (`game level tiers (spec 0021) [WEB-LEVEL-003] shows no model label on the level cards`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-08 · commit ce5746e (+ uncommitted changes)

- Criteria: WEB-LEVEL-004
- Red: 1 failing test(s) before implementation (`game level tiers (spec 0021) [WEB-LEVEL-002] [WEB-LEVEL-004] shows no model section in the AI Agent modal`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed

### 2026-11-09 · commit ce5746e (+ uncommitted changes)

- Criteria: ENG-LEVEL-007, WEB-LEVEL-005
- Red: 2 failing test(s) before implementation (`packages/engine/tests/test_game_levels.py::test_final_node_is_the_protected_agent_and_validation_names_the_final_node`, `final node naming (spec 0021) [WEB-LEVEL-005] explains the final node and heads its objective System Instruction`)
- Green: 2 passing test(s)
- Gate: `mise run check` passed
