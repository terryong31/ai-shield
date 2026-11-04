# Contributing

Thanks for helping. This project runs on **spec-driven + test-driven
development**. Please read this page before opening a PR.

## Setup

```bash
mise install && mise run setup
mise run check     # should be green on a fresh clone
```

## The workflow

1. **Open or find an issue** describing the problem.
2. **Spec it.** Find the covering spec in [`specs/`](specs/README.md) or create
   one with `mise run spec:new <slug>`. Open a PR with the spec alone
   (status `Draft`). A maintainer moves it to `Accepted`.
3. **Run the SDD cycle:** `mise run sdd:start <NNNN>`, write the tagged tests,
   then `sdd:red` (proves they fail), implement, `sdd:green`, and `sdd:verify`
   (the full gate). Update `docs/reference/` and `CHANGELOG.md`.
4. **Close it:** `mise run sdd:done` marks the spec `Implemented` and appends
   the verification record. Commit that with your change; CI rejects
   `Implemented` specs without one.

Refactors, docs-only changes and dependency bumps don't need a spec.

The step-by-step version is in [docs/how-to/write-a-spec.md](docs/how-to/write-a-spec.md)
and [docs/tutorials/03-your-first-spec-driven-change.md](docs/tutorials/03-your-first-spec-driven-change.md).

## Rules that reviewers enforce

- The engine never imports web frameworks or databases, and never reads env vars.
- The web client uses only the generated contract types.
- No secrets in prompts, logs or audit records.
- Detection changes include before/after `mise run eval` numbers.
- Never weaken a test to make it pass.

The full list is in [AGENTS.md](AGENTS.md), which humans and AI agents share.

## Commits and PRs

- Use [Conventional Commits](https://www.conventionalcommits.org) (`feat(engine): …`, `fix(api): …`, `docs: …`).
- Keep each PR focused on one spec or one refactor. Fill in the PR template.
- CI must be green before review.

## AI-assisted contributions

Welcome, under the same rules. Agents read `AGENTS.md`; Claude Code users also
get project skills (`/new-spec`, `/tdd`, `/run-eval`) and reviewer subagents.
The human author is responsible for every line they submit.
