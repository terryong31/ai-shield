# 0032 — System .env-only API keys (no user-entered API keys)

- **Status:** Accepted
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-17
- **Related:** [0031-live-api-keys-and-real-metrics](../0031-live-api-keys-and-real-metrics/spec.md)

## Problem

In Spec 0031, the web UI and `GameRunRequest` allowed players to type and submit `jev_api_key` and `ai_api_key` through a modal and node settings inputs. Players should **never** be allowed to enter their own API keys in `/game` for `jev`, `safety_check`, or `agent_review`. Instead, API keys must come strictly from the backend system configuration (`.env`), and if a required key is missing in `.env`, the node must be disabled and clicking it should simply show a toast informing the user to add the API key in the system (`.env`).

## Goals

- Remove all user API-key input fields and the API key entry modal from `/game`.
- Remove `jev_api_key`, `ai_api_key`, and `ai_provider` from `GameRunRequest` so the gateway uses only keys configured in `.env`.
- Keep `jev`, `safety_check`, and `agent_review` disabled in the Tools panel when the corresponding `.env` key is missing, and show a toast instructing the user to add the API key in the system (`.env`) when clicked.

## Non-goals

- Removing the Custom Sandbox (`level_id: "custom"`) BYOK form on `/`, which is a separate paid-tier feature (Spec 0022).
- Changing engine real-latency or token-cost calculation.

## Behaviour

- **API (`apps/api`)**:
  - `GameRunRequest` does not accept `jev_api_key`, `ai_api_key`, or `ai_provider`.
  - `GET /api/v1/game/levels` continues to report `jev_key_configured` (from `TYPESAFE_API_KEY` in `.env`) and `ai_key_configured` (from `GROQ_API_KEY` / `GOOGLE_API_KEY` in `.env`).
  - `POST /api/v1/game/run` uses only `container.jev_client` and `container.game_agent` / `container.game_agents` configured from `.env`.
- **Web (`apps/web`)**:
  - No modal or input exists in `/game` for entering a Jev or AI API key (`isApiKeyModalOpen`, `jevApiKey`, `aiApiKey`, `aiKeyProvider` removed).
  - When `jevKeyConfigured` is `false`:
    - `jev` card is disabled (`aria-disabled="true"`, `draggable="false"`, locked footer).
    - Clicking `jev` does not add the node to the board and shows a toast telling the user to add `TYPESAFE_API_KEY` in the system `.env`.
  - When `aiKeyConfigured` is `false`:
    - `safety_check` and `agent_review` cards are disabled (`aria-disabled="true"`, `draggable="false"`, locked footer).
    - Clicking them (when signed in) does not add the node to the board and shows a toast telling the user to add `GROQ_API_KEY` or `GOOGLE_API_KEY` in the system `.env`.

## Acceptance criteria

- **API-LIVE-002**: Given `GameRunRequest`, when inspected or submitted, then per-run `jev_api_key` and `ai_api_key` fields do not exist and `/api/v1/game/run` relies exclusively on `.env`-configured `container.jev_client` and `container.game_agent` / `container.game_agents`.
- **WEB-LIVE-002**: Given `/game` when `jev_key_configured` or `ai_key_configured` is `false`, then no UI input or modal exists to enter Jev or AI API keys, the corresponding nodes are disabled and cannot be placed in the workflow, and clicking them displays a toast instructing the user to add the API key in the system `.env`.

## Security & privacy considerations

- Eliminates client-side transmission of Jev / AI check API keys on standard game runs; secrets live exclusively in backend `.env`.

## Evaluation impact

- None.

## Open questions

- None.
