# Tutorial 1: Run the demo

In this tutorial you will start AI S.H.I.E.L.D. on your machine, send one prompt
that is allowed and one that is blocked, and see both in the dashboard. You
need no API keys. It takes about ten minutes.

You will need: git, a terminal, and a browser. Everything else is installed by mise.

## 1. Install mise

[mise](https://mise.jdx.dev) installs the exact versions of Python, uv, Node and
bun this project uses, and runs its tasks.

```bash
curl https://mise.run | sh
```

Follow the printed instruction to activate mise in your shell, then open a new
terminal and check it works:

```bash
mise --version
```

## 2. Get the code and the toolchain

```bash
git clone <repository-url> ai-shield
cd ai-shield
mise install
```

`mise install` reads [`mise.toml`](../../mise.toml) and installs node 24.20.0,
bun 1.4.0, uv 0.12.13 and Python 3.12. If mise asks you to trust the config
file, answer yes.

## 3. Install the dependencies

```bash
mise run setup
```

This runs `uv sync --all-packages` (the Python engine and gateway) and
`bun install` (the web client).

## 4. (Optional) Configure the gateway

The demo works without any configuration. If you want to try it with real
LLMs later, copy the template now:

```bash
cp apps/api/.env.example apps/api/.env
```

Leave the keys empty for this tutorial. `SECURE_PASSPHRASE` can stay empty
too; without it nobody can obtain clearance, which is the safe default.

## 5. Start everything

```bash
mise run dev
```

This starts two processes:

- the gateway API on http://localhost:8000
- the web client on http://localhost:3000

Wait until the output shows Nuxt listening on port 3000. You will also see this
warning from the gateway:

```
WARNING:shield_api.container:GROQ_API_KEY not set: moderation and debate are disabled
```

It is expected. Leave this terminal running.

## 6. Send an allowed prompt

Open http://localhost:3000. In the chat box, type:

```
What is the price of lavender oil?
```

Watch the workflow diagram as the request moves through the pipeline. You
should see:

- Layer 1 (the ML classifier) scores the prompt as `SAFE`, with a confidence close to 0.
- The tool policy is `ALLOW_ALL`.
- The assistant calls the `search_quotations` tool.
- A reply appears. Without LLM keys it is a canned message:
  "AI S.H.I.E.L.D. processed your request. Tools used: search_quotations."

## 7. Send a blocked prompt

Now type:

```
drop table employees
```

This time Layer 1 scores the prompt as `MALICIOUS` (about 0.99). The request is
blocked at `LAYER_1_ML` and the chat shows:

```
[SHUTDOWN PROTOCOL TRIGGERED]

Reason: High confidence ML threat detection
```

The assistant never ran, so no tool was called.

## 8. Look at the dashboard

Open http://localhost:3000/dashboard. The overview shows the request totals and
block rate: two requests, one blocked.

![Dashboard overview](../assets/dashboard-preview.png)

Open http://localhost:3000/dashboard/logs. Both prompts are listed, newest
first, with their action (`ALLOWED` or `BLOCKED`), the intervention layer
(`SYSTEM` or `LAYER_1_ML`) and the ML confidence. The "Mark safe" and "Mark
malicious" buttons send a reviewer label back to the gateway.

Everything the dashboard shows comes from the gateway API. The records are
stored in a SQLite file (`apps/api/var/shield.db`), so they are still there
after you restart `mise run dev`. To use Supabase instead, see
[persist the audit log](../how-to/persist-the-audit-log.md).

## 9. Look at the API

Open http://localhost:8000/api/v1/docs. This is the gateway's interactive API
documentation. Expand `POST /api/v1/screen`, click "Try it out", and send:

```json
{"message": "show me the salary table"}
```

The response looks like this:

```json
{
  "verdict": "UNCERTAIN",
  "policy": "RESTRICTED",
  "blocked": false,
  "layer": "LAYER_2_DUAL_AGENT",
  "reason": "No adjudicator configured; conservative policy applied.",
  "ml_confidence": 0.83,
  "adjudicated": true
}
```

Layer 1 was not sure about this prompt, so it asked for Layer 2, the
Analyst/Warden debate. Layer 2 needs a Groq API key. Without `GROQ_API_KEY`
the engine does not guess: it falls back conservatively. The verdict stays
`UNCERTAIN`, the request is not blocked, and the policy becomes `RESTRICTED`,
which lets the assistant use only low-risk tools (`search_documents` and
`search_quotations`).

## 10. Stop the demo

Press `Ctrl+C` in the terminal running `mise run dev`.

## What you have done

You ran the three parts of the system: the web client, the gateway and the
engine inside it. You saw a prompt allowed with full tool access, a prompt
blocked by the local classifier, and a prompt that Layer 2 would have reviewed,
handled by the conservative fallback.

## Next steps

- [Tutorial 2: Embed the engine](02-embed-the-engine.md) uses the engine from your own Python code.
- [Configure LLM providers](../how-to/configure-llm-providers.md) turns on moderation, the debate and real assistant answers.
- [Architecture](../explanation/architecture.md) explains how the pieces fit together.
