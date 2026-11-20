# Plan — 0031 Live Jev & AI node API keys and real measured latency/cost

## Engine (`packages/engine`)

1. **`packages/engine/src/shield_engine/ports.py`** & **`packages/engine/src/shield_engine/testing.py`**:
   - Add `JevEvaluation` dataclass (`probability: float`, `input_tokens: int`, `output_tokens: int = 0`) and `JevClient` `Protocol` (`async def evaluate_noul(self, state: str, question: str, *, model: str = "jev-latest") -> JevEvaluation`).
   - Add `ScriptedJevClient` to `shield_engine.testing`.
2. **`packages/engine/src/shield_engine/game/__init__.py`**:
   - Remove `_score_jev_noul`, `_SAFETY_PATTERNS`, and `_DEEP_ATTACK_PATTERNS` simulated evaluation for `jev`, `safety_check`, and `agent_review`.
   - Add `jev_client: JevClient | None = None` and `check_model: UsageChatModel | None = None` to `evaluate_message`, `run_wave`, and `run_single_message` (and `run_custom_wave` / `run_custom_message`).
   - Measure real `latency_ms` via `time.perf_counter()` on every node hop.
   - Calculate real token `cost_usd` for `jev` (`input_tokens * 0.042 / 1_000_000`), `safety_check`, and `agent_review` from actual token usage.

## API (`apps/api`)

3. **`apps/api/src/shield_api/providers/typesafe.py`**, **`settings.py`**, **`container.py`**, **`schemas.py`**, **`routers/game.py`**:
   - Add `HttpJevClient` calling `POST https://api.typesafe.ai/v1/systemone`.
   - Add `TYPESAFE_API_KEY` to `Settings` and `jev_client: JevClient | None` to `Container`.
   - Add `jev_key_configured: bool` and `ai_key_configured: bool` to `GameCatalogResponse`.
   - Add `jev_api_key: SecretStr | None = None`, `ai_api_key: SecretStr | None = None`, `ai_provider: ProviderId = "openai"` to `GameRunRequest`.
   - Regenerate OpenAPI contract and web types (`mise run contract`).

## Web (`apps/web`)

4. **`apps/web/app/utils/gameBoard.ts`** & **`apps/web/app/pages/game.vue`**:
   - Update `canUseNodeKind` and add `nodeKeyRequirement(kind, keys)` returning `"Insert Jev API key to continue"` when `jev` has no key and `"Enter API key to continue"` when `safety_check` / `agent_review` have no key.
   - Disable unconfigured AI / Jev tool cards until a key is present, and open an API key modal / inline input when clicked so the player can enter their Jev or AI API key and immediately unlock the node.
   - Display real backend-measured hop latency and cost on nodes and in modals.
