# Configure LLM providers

The game's agent levels run a real model when one is configured. Keys go in
[Infisical](manage-secrets.md) (`dev /api` and `prod /api`) and are read once at startup by
[`container.py`](../../apps/api/src/shield_api/container.py).

| Level | Agent tier | Model | Needs |
| --- | --- | --- | --- |
| Easy | none | classification only, no model | nothing |
| Medium | `standard` | `GAME_MODEL_STANDARD`, else `GEMINI_MODEL` (Gemini) or `GROQ_CHAT_MODEL` (Groq) | `GOOGLE_API_KEY` or `GROQ_API_KEY` |
| Hard | `budget` | `GAME_MODEL_BUDGET` (default `openai/gpt-oss-20b`) on Groq | `GROQ_API_KEY` |
| Custom | the player's own | the player's provider and model (BYOK) | the player's key, per run |

Without a key for a tier, that level runs a deterministic offline stand-in, so
the game still works and tests need no network.

## Enable Gemini (standard tier)

1. Create a Gemini API key in Google AI Studio.
2. Add `GOOGLE_API_KEY` to Infisical ([how](manage-secrets.md#add-or-change-a-secret)).
   `GEMINI_MODEL` is optional (default `gemini-3.5-flash-lite`).

## Enable Groq (budget tier, and standard without Gemini)

1. Create an API key in the Groq console.
2. Add `GROQ_API_KEY` to Infisical. Optional: `GAME_MODEL_BUDGET` (default `openai/gpt-oss-20b`)
   and `GROQ_CHAT_MODEL` (default `openai/gpt-oss-120b`, the standard tier without a Google key).

Groq shut down its Llama chat and Llama Guard models for free and developer
keys on 2026-08-16, and Google no longer serves `gemini-2.x` to new keys. Boards
saved with those IDs still run: the engine maps them to the replacements above,
and `Safety check` uses `openai/gpt-oss-safeguard-20b`.

## Check

Restart the gateway (Infisical values are read only when the process starts), then:

```bash
curl -s http://localhost:8000/api/v1/health
```

`agent_tiers` lists the tiers that now run a live model, for example
`["budget", "standard"]`. A wave on Medium or Hard then reports `agent_mode: "live"`
and is recorded on the leaderboard for signed-in players.

## Failure behaviour

| Situation | Behaviour |
| --- | --- |
| No key for a tier | Offline stand-in; `agent_mode: "simulated"`; not recorded on the leaderboard |
| Provider error during a run | `503`; the run is not counted against the quota |
| Custom sandbox provider error | `502`; the player's key is never logged or echoed |

## Add another provider

Implement `UsageChatModel` (one async `complete_with_usage` method returning
`ChatCompletion`) and wire it in `build_container()`.
[`providers/gemini.py`](../../apps/api/src/shield_api/providers/gemini.py) is a
complete example. For the custom sandbox, add the provider to the allowlist in
[`providers/byok.py`](../../apps/api/src/shield_api/providers/byok.py) with a
fixed HTTPS base URL; never accept a URL from the player.
