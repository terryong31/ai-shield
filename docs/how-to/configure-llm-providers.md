# Configure LLM providers

The game's agent levels run a real model when one is configured. Keys go in
`apps/api/.env` (or the process environment) and are read once at startup by
[`container.py`](../../apps/api/src/shield_api/container.py).

| Level | Agent tier | Model | Needs |
| --- | --- | --- | --- |
| Easy | none | classification only, no model | nothing |
| Medium | `standard` | `GAME_MODEL_STANDARD`, else `GEMINI_MODEL` (Gemini) or `GROQ_CHAT_MODEL` (Groq) | `GOOGLE_API_KEY` or `GROQ_API_KEY` |
| Hard | `budget` | `GAME_MODEL_BUDGET` (default `llama-3.1-8b-instant`) on Groq | `GROQ_API_KEY` |
| Custom | the player's own | the player's provider and model (BYOK) | the player's key, per run |

Without a key for a tier, that level runs a deterministic offline stand-in, so
the game still works and tests need no network.

## Enable Gemini (standard tier)

1. Create a Gemini API key in Google AI Studio.
2. Add it to `apps/api/.env`:

   ```dotenv
   GOOGLE_API_KEY=...
   GEMINI_MODEL=gemini-2.5-flash
   ```

## Enable Groq (budget tier, and standard without Gemini)

1. Create an API key in the Groq console.
2. Add it to `apps/api/.env`:

   ```dotenv
   GROQ_API_KEY=gsk_...
   GAME_MODEL_BUDGET=llama-3.1-8b-instant
   GROQ_CHAT_MODEL=llama-3.3-70b-versatile   # standard tier when there is no Google key
   ```

## Check

Restart the gateway (`mise run api:dev` reloads on code changes, not on `.env`
changes), then:

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
