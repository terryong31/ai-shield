# 0051 — Campaign levels v2

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-26
- **Related:** [audit of 0050](../0050-campaign-redesign/audit.md) (evidence, ladder and level verdicts), [0050](../0050-campaign-redesign/spec.md), [0039](../0039-campaign-levels-and-difficulty-leaderboard/spec.md)

## Problem

The 23 levels have one solution (audit F1 to F3). Hard is not hard because of attacks: the agent leaks 1 of 48 with no
checks, but refuses normal requests (F5, F6). Dual-use control and most limits are not necessary to win (F10, F11).

## Goals

- 19 levels. Each adds one idea that its solution needs.
- Difficulty that rises, and a report that proves it.
- Attacks that look like normal work, each with a normal twin.

## Non-goals

- New node types.
- Procedural or model-generated prompts at run time.

## Behaviour

### Content rules

- The catalogue, floors, limits and mastery of each level are the table "New ladder" in the audit.
- Each level has one hidden wave of 24 prompts (12 attacks, 12 normal), and a briefing with one example of each family.
- Each wave has at least 4 attack families with 2 or more prompts each. The briefing example of a family uses other words than the wave, except on Easy 1, whose hint uses the key phrases (WEB-LADDER-003).
- Each attack family has at least one normal twin: the same topic and, on agent levels, the same tool.
- On Medium and Hard, at most 2 of 12 attacks contain the tool name, and at most 2 start with a known override verb.
- Prompts are written and reviewed by a person. They contain no real personal data, keys or companies.

### Easy is a guided course

Decided on 2026-11-26 after calibration: one general Jev node cleared Level 1 alone.

| Level | Tools on the palette | Tour | Limits | Mastery |
| --- | --- | --- | --- | --- |
| 1 | Word filter, length limit | Place, wire, run, read the result | None | 2 nodes or fewer |
| 2 | Adds text cleaner and secret scanner | Clean first, then scan | None | 2 nodes or fewer |
| 3 | Same as level 2 | Precise scanner patterns | 3 nodes | No word filter |
| 4 | ML filter only | Train rows, set thresholds | 40 training rows | Stop all 12 attacks |
| 5 | All tools (exam) | None | 2 nodes, list latency 6 ms per prompt | A perfect wave |

The latency limit of level 5 leaves no room for a paid check (Jev takes 12 ms), so the exam needs the free tools.
These rows replace levels 1 to 5 of the audit table "New ladder".

### Live calibration changes

Decided on 2026-11-27 after the live calibration. These rows replace the matching values of the audit table "New ladder".

| Level | Change | Reason |
| --- | --- | --- |
| 6 HR Handbook | No Jev, safety check, LLM review or ML filter on the palette. Mastery: no word filter. The agent also reads salary records when staff ask about pay. | One safety check cleared it alone, and the agent refused pay requests without the player's rules. |
| 9 Lost in Translation | Attack floor 12 (was 11). | One generic Jev or safety check stopped 11 of 12 attacks; the reference board stopped 12 in every run. |
| 10 Express Lane | Cost limit $0.0008 (was $0.0012). Mastery: list cost $0.0005 or less. | Jev on all 24 prompts lists $0.0012, so it fit the old limit. |

### Agent

- Medium keeps the guard lines of the base prompt. Hard removes "never reveal" and "never follow" and tells the agent to do each requested action. The player's rules and checks are the defence.
- User text stays inside `wrap_untrusted()` on all levels.
- An attack has a severity. A `critical` leak is a canary leak or a restricted tool that moves money, deletes data or exports data.

### Calibration

`mise run levels:calibrate` runs the lazy bots and the reference board of each level with the real models and writes a
report with the level version, model names, results and date. It never runs in CI. CI checks that each released level
has a passing report for its present version.

## Acceptance criteria

- **ENG-LADDER-001**: Given the catalogue, then it has 19 levels (5 Easy, 7 Medium, 7 Hard) in the audit order, with those floors, limits and mastery goals.
- **ENG-LADDER-002**: Given any level, then the wave follows the content rules on counts, families and twins, and no wave text equals a briefing example after clean-up.
- **ENG-LADDER-003**: Given Medium and Hard wave attacks, then the tool-name and override-verb limits hold.
- **ENG-LADDER-004**: Given the offline agent, then block-all, allow-all, briefing-memoriser, campaign-regex and briefing-ML bots do not clear a level, except level 1 (memoriser, campaign regex) and level 4 (briefing ML).
- **ENG-LADDER-010**: Given the calibration report, then no level is cleared by one model node with a general setting: Jev with the general question, the default safety check, or Prompt Guard. The general question is fixed in the calibration command.
- **ENG-LADDER-011**: Given any agent level, then the agent prompt tells the agent to answer a request by calling the tool that fits it, not from memory. (Found in live calibration: without this line, Gemini Flash Lite helped 4 of 12 normal prompts on Medium 1.)
- **API-LADDER-004**: Given a `gemini-*` model, then `GeminiChatModel` asks for JSON output (`response_mime_type="application/json"`), so a reply never ends as a malformed native function call with empty text; other models (Gemma) are sent no JSON setting.
- **ENG-LADDER-012**: Given the live agent calls a tool, then it gets the tool result and one more turn, and makes at most 2 model calls for a prompt. The tools of both turns count for the verdict, a canary in the reply of either turn is a leak, and the tokens of both turns add up. (Found in live calibration: the agent looks up an order before it issues the credit.)
- **ENG-LADDER-013**: Given the live agent, then it asks the model for at most 600 output tokens, which leaves room for the hidden reasoning of a reasoning model and the JSON reply. (Found in live calibration: at 300 tokens, `gpt-oss-20b` ended 3 of 46 Hard replies with no answer.)
- **ENG-LADDER-014**: Given a native tool call that a model wraps in a call named `commentary` (`{"name": "commentary", "arguments": {"name": <tool>, ...}}`), or names it with a prefix such as `tool:` or `functions.`, then the agent reads it as a call to the inner tool. (Found in live calibration: `gpt-oss-20b` on Groq.)
- **ENG-LADDER-015**: Given any campaign level, then a run clears only when all 12 attacks are stopped and all 12 normal prompts are helped. One leaked attack or one stopped or unhelped normal prompt loses the run. Every level's floors are 12 and 12. (Owner's rule, 2026-11-27.) Easy 4 mastery is 20 training rows or fewer; Easy 5 mastery is 1 check node.
- **ENG-LADDER-005**: Given the reference board of a level, then it clears offline; given the same board without the control for the new idea, then it does not clear.
- **ENG-LADDER-006**: Given two consecutive levels of a tier, then the best lazy-bot value `A/At x N/Nt` does not rise by more than 0.05.
- **ENG-LADDER-007**: Given each limit of a level, then the reference board without attention to that limit breaks it, so the limit binds.
- **ENG-LADDER-008**: Given a Hard level, then the agent prompt has no guard lines, has the eager line, and wraps user text; given Medium, then the guard lines are present.
- **ENG-LADDER-009**: Given a dual-use level, then switching the tool off always, or never, does not clear.
- **DEV-LADDER-001**: Given a released level with no passing calibration report for its version, then the CI check fails and names the level. A passing report has at least 4 of 5 reference clears (owner, 2026-11-27: under "one miss loses" the live agent can slip on one run), a standard deviation of 700 points or less over the cleared runs, and no lazy-bot clear. (Changed from 150 by the owner on 2026-11-27: one normal prompt on the live agent moves the score by about 600 points.)
- **API-LADDER-001**: Given a level ID that was removed, then run and save return `404`, and a migration deletes its saved boards and scores.
- **API-LADDER-002**: Given free players, then Easy 1 to 3 and Medium 1 to 2 are open and all other levels return `403`.
- **WEB-LADDER-003**: Given a campaign level with attack examples, then the game header has a free `Hint` button beside `Guide` that opens a modal with the examples (family and text). It changes no score and no star. On Easy 1 the examples use the wave's key phrases, two or three for each family, so a beginner can build a perfect word filter (owner, 2026-11-27); the other levels keep one example in other words for each family.
- **WEB-LADDER-002**: Given Easy levels 1 to 4, then each has a guided tour that points at the tools it teaches, ends at `Run wave`, and has no step for the removed test box; level 5 and later have no tour.
- **API-LADDER-003**: Given a level with a training row limit, when a player trains the ML filter with more rows, then the response is `422` and names the limit, and no training run is used.
- **WEB-LADDER-001**: Given level selection, then each level tile shows its number and title with no summary text (owner, 2026-11-27), and the briefing of every level shows (owner, 2026-11-27): the level's one new idea with no heading; "Objective" with the three star goals (first star: clear the level; second star: score 9,250 or more; third star: the mastery goal); then the same star rating and high score as before. It shows no attack examples and no facts table.

## Security & privacy considerations

The eager agent calls sandboxed tools that only return text. No real system is reached. The secret is a canary.

## Evaluation impact

Plausible abuse leaked 12 of 40 on the eager agent, against 3 of 48 for the present attacks (audit, section 2).
Acceptance is the calibration report. Human targets are in section 7 of the audit and need a person test.

## Replaced criteria

During the cycle, each one gets the text `Replaced by <new ID> (0051).`, and its test is changed to test the new behaviour and also carries the new ID.

| Old | Spec | New | What changes |
| --- | --- | --- | --- |
| ENG-CAMP-001 | 0039 | ENG-LADDER-001 | 19 levels, not 23 |
| API-CAMP-001 | 0039 | ENG-LADDER-001, API-LADDER-002 | The catalogue has 19 levels. The free levels stay Easy 1 to 3 and Medium 1 to 2 |
| WEB-CAMP-004 | 0040 | WEB-LADDER-001 | The briefing also shows one example of each family |
| WEB-CAMP-007 | 0040 | WEB-LADDER-002 | Easy 1 to 4 have a tour, and no tour step points at the removed test box |
| ENG-FAIR-001 (floors) | 0050 | ENG-LADDER-015 | A run clears only with no miss: the floors are 12 and 12 |

## Open questions

Decided on 2026-11-26: 19 levels, no notice (no players yet), and saves of removed levels are deleted.

Also decided: levels get new numbers and a level version, because saves of changed levels are not compatible.

Calibration steps before content is written (not open questions):

1. Measure Medium first. It was not measured, because the dev Gemini quota ended.
2. The Hard leak rate of 30% comes from 20 prompts and one model. If calibration shows less than 25%, choose a weaker model.

## Verification

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: ENG-LADDER-004, ENG-LADDER-005, ENG-LADDER-006, ENG-LADDER-007, ENG-LADDER-009, ENG-LADDER-010, DEV-LADDER-001, API-LADDER-001, WEB-LADDER-001
- Red: 9 failing test(s) before implementation (`packages/engine/tests/test_campaign_ladder.py`, `packages/engine/tests/test_campaign_ladder.py`, `packages/engine/tests/test_campaign_ladder.py`)
- Green: 9 passing test(s)
- Gate: `mise run check` passed

### 2026-11-27 · commit 9c2136c (+ uncommitted changes)

- Criteria: WEB-LADDER-003
- Red: 1 failing test(s) before implementation (`Level hint (spec 0051) [WEB-LADDER-003] has a free Hint button beside Guide that lists the attack examples`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed
