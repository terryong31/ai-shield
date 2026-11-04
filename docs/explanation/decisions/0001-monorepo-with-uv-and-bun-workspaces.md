# 0001. Monorepo with uv and bun workspaces

- **Status:** Accepted
- **Date:** 2026-09-23

## Context

The project was a single Next.js application with a Python prediction function
deployed beside it (`api/predict/index.py`) and a separate `ml-endpoint/`
folder holding the training script and pickled models. The refactor splits it into a Python engine, a Python gateway and a
TypeScript web client ([ADR 0002](0002-engine-gateway-split.md)). These parts
change together often: an engine change alters gateway events, which alters
the web client's types. Two languages need dependency management, and
contributors (human and AI) need one obvious way to install, test and run
everything.

Options considered: separate repositories per part; one repository with ad-hoc
scripts; one repository with native workspace tooling per language and a
shared task runner.

## Decision

Keep all three parts in one repository:

- Python packages form a **uv workspace** (`pyproject.toml` at the root lists
  `packages/engine` and `apps/api`; one `uv.lock`). The gateway depends on the
  engine as a workspace source.
- JavaScript packages form a **bun workspace** (`package.json` lists `apps/web`;
  one `bun.lock`).
- **mise** pins the toolchain (Python, uv, Node, bun) and defines every task
  (`mise run setup`, `dev`, `test`, `check`, …) in `mise.toml`.
- Shared lint, type-check and test configuration lives in the root `pyproject.toml`.

## Consequences

- One pull request can change the engine, the gateway, the contract and the web
  client atomically, and one CI run checks them together.
- A single command set works for everyone, including agents: `AGENTS.md` tells
  them to use `mise run …` and never `pip` or `npm`.
- Lockfiles are unified per language, so the engine and gateway always resolve
  the same versions.
- The engine is still independently packageable (`shield-engine` has its own
  `pyproject.toml`, build backend and version).
- Contributors must install mise. Docker builds must use the repository root
  as context to see the lockfiles.
- CI cannot yet skip unaffected parts; every push runs every job.
