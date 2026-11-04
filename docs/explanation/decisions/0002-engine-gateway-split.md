# 0002. Split the engine from the gateway

- **Status:** Accepted
- **Date:** 2026-09-23

## Context

Detection logic lived inside the Next.js chat route (`app/api/chat/route.ts`),
interleaved with HTTP streaming, Supabase logging, the Layer 2 agents and demo
tool calls. As a result it could not be embedded in another application,
evaluated offline against a dataset, or unit-tested without a web server and
live LLM keys. The project aims at research use (reproducible measurements)
and commercial use (embedding in other people's LLM applications), and both
need the detector as a library.

## Decision

Separate the system into:

- **`packages/engine` (`shield_engine`)**: a framework-free Python library.
  `Shield` routes a prompt through a classifier, optional moderator and optional
  adjudicator to a `Decision`. All external services are injected through
  structural `Protocol` ports (`ChatModel`, `FeedbackStore`, `Classifier`,
  `Moderator`, `Adjudicator`). Required dependencies are scikit-learn and joblib;
  provider SDKs are optional extras under `adapters/`. The engine reads no
  environment variables and never sees credentials; the host passes a
  `Clearance` level.
- **`apps/api` (`shield_api`)**: a thin FastAPI gateway that maps HTTP to engine
  calls, runs the demo assistant and tools under the engine's tool policy, and
  owns persistence. It contains no detection logic. All concrete adapters are
  chosen in one composition root, `container.py`.

## Consequences

- The engine can be installed and used on its own (`uv add shield-engine`),
  evaluated with `shield-engine eval`, and tested with shipped doubles
  (`shield_engine.testing`) without network access.
- Specs 0001–0006 cover the engine and 0007 the gateway; engine coverage floor
  is 90%, gateway 85%.
- Swapping a provider, audit store or classifier is a change in `container.py`
  only.
- The gateway duplicates some vocabulary (HTTP schemas mirror engine enums),
  and engine events must be translated to wire events in `services/chat.py`.
- Two Python packages must be versioned and kept compatible, which the uv
  workspace makes routine ([ADR 0001](0001-monorepo-with-uv-and-bun-workspaces.md)).
