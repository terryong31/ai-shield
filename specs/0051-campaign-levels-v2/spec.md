# 0051 — Campaign levels v2

- **Status:** Accepted
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
- Each wave has at least 4 attack families with 2 or more prompts each. The briefing example of a family uses other words than the wave.
- Each attack family has at least one normal twin: the same topic and, on agent levels, the same tool.
- On Medium and Hard, at most 2 of 12 attacks contain the tool name, and at most 2 start with a known override verb.
- Prompts are written and reviewed by a person. They contain no real personal data, keys or companies.

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
- **ENG-LADDER-005**: Given the reference board of a level, then it clears offline; given the same board without the control for the new idea, then it does not clear.
- **ENG-LADDER-006**: Given two consecutive levels of a tier, then the best lazy-bot value `A/At x N/Nt` does not rise by more than 0.05.
- **ENG-LADDER-007**: Given each limit of a level, then the reference board without attention to that limit breaks it, so the limit binds.
- **ENG-LADDER-008**: Given a Hard level, then the agent prompt has no guard lines, has the eager line, and wraps user text; given Medium, then the guard lines are present.
- **ENG-LADDER-009**: Given a dual-use level, then switching the tool off always, or never, does not clear.
- **DEV-LADDER-001**: Given a released level with no passing calibration report for its version, then the CI check fails and names the level. A passing report has 5 of 5 reference clears, a standard deviation of 150 points or less, and no lazy-bot clear.
- **API-LADDER-001**: Given a level ID that was removed, then run and save return `404`, and a migration deletes its saved boards and scores.
- **API-LADDER-002**: Given free players, then Easy 1 to 3 and Medium 1 to 2 are open and all other levels return `403`.
- **WEB-LADDER-001**: Given level selection, then each level shows its one new idea, and the briefing shows floors, limits, the mastery goal and one example of each attack family.

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

## Open questions

Decided on 2026-11-26: 19 levels, no notice (no players yet), and saves of removed levels are deleted.

Also decided: levels get new numbers and a level version, because saves of changed levels are not compatible.

Calibration steps before content is written (not open questions):

1. Measure Medium first. It was not measured, because the dev Gemini quota ended.
2. The Hard leak rate of 30% comes from 20 prompts and one model. If calibration shows less than 25%, choose a weaker model.
