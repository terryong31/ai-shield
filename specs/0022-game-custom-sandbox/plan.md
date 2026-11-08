# 0022 — Custom sandbox: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

- **Engine:** `parse_custom_dataset(csv_text, profile)` and
  `validate_custom_profile(profile)` in `shield_engine/game/custom.py`, and
  `run_custom_wave(board, *, profile, messages, classifier, agent)` that
  reuses the level wave loop (refactor `run_wave` to share it).
- **Gateway:** `GameRunRequest.custom: CustomRunSchema | None` with
  `agent`, `dataset` (rows) and `model` (`provider`, `model`, `api_key:
  SecretStr`). A `build_byok_model(provider, model, key)` factory in
  `shield_api/demo/byok.py` maps each provider to a fixed endpoint. The
  router requires `tier == "paid"`, builds the client, runs, and maps
  provider errors to `502`. A logging filter and the existing error handlers
  never see the key, because it stays a `SecretStr` until the client is
  built.
- **Web:** a `Custom` card on `/`; `level=custom` in `game.vue` loads an
  editable profile; `useCustomSandbox()` keeps the key in a plain `ref`;
  `parseDatasetCsv` in `app/utils/` mirrors the engine rules for instant
  feedback.

## Interfaces

```python
class ModelProvider(StrEnum): OPENAI = "openai"; GROQ = "groq"; GOOGLE = "google"

def parse_custom_dataset(csv_text: str, profile: AgentProfile) -> tuple[LevelMessage, ...]: ...
def validate_custom_profile(profile: AgentProfile) -> None: ...
async def run_custom_wave(board, *, profile, messages, classifier=None,
                          agent: UsageChatModel) -> WaveResult: ...
```

HTTP: `GameRunRequest.level_id` accepts `"custom"`; new `custom` field;
`GameRunResponse.agent_mode` gains `"custom"`; new `502` response.

## Boundaries check

- [ ] `packages/engine` still imports nothing from web frameworks, databases or `shield_api`
- [ ] Credentials stop at the gateway: the engine receives a `UsageChatModel`, never a key
- [ ] `apps/web` still talks to the backend only through the published OpenAPI contract
- [ ] Threat model updated for client keys

## Alternatives considered

| Option | Why not |
| --- | --- |
| Accept any OpenAI-compatible base URL | SSRF into the gateway's network |
| Store keys encrypted per account | Key custody and breach risk for a sandbox feature |
| Run the player's model from the browser | Exposes the key to page scripts and skips the server-side judge |

## Risks and rollback

- A key could leak through an unexpected log path. API-SANDBOX-003 tests the
  response, the logs and the audit log; review new logging calls in the
  router.
- Rollback: hide the `Custom` card and reject `level_id: "custom"`.
