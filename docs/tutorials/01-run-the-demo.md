# Tutorial 1: Run the game

In this tutorial you will start `ai-shield` on your machine, build a defence board, run a level's attack wave, read your results, and look at the admin console. You need no API keys. It takes about ten minutes.

You will need: git, a terminal, and a browser. Everything else is installed by mise.

## 1. Install mise

[mise](https://mise.jdx.dev) installs the exact versions of Python, uv, Node and bun this project uses, and runs its tasks.

```bash
curl https://mise.run | sh
```

Follow the printed instruction to activate mise in your shell, then open a new terminal and check it works:

```bash
mise --version
```

## 2. Get the code and the toolchain

```bash
git clone <repository-url> ai-shield
cd ai-shield
mise install
```

`mise install` reads [`mise.toml`](../../mise.toml) and installs node 24.20.0, bun 1.4.0, uv 0.12.13 and Python 3.12. If mise asks you to trust the config file, answer yes.

## 3. Install the dependencies

```bash
mise run setup
```

This runs `uv sync --all-packages` (the Python engine and gateway) and `bun install` (the web client). It also installs the git hooks (`lefthook install`). The hooks check your commits and run the full gate before each push. See [Work with CI and the git hooks](../how-to/work-with-ci-and-git-hooks.md).

## 4. (Optional) Configure the gateway

The game works without any configuration. If you want to try the admin console or real LLMs later, copy the template now:

```bash
cp apps/api/.env.example apps/api/.env
```

Leave the provider keys empty for this tutorial. The admin console (`/_console`) needs Supabase: with `SUPABASE_URL` and `SUPABASE_KEY` set, run `mise run admin:create you@example.com` to make an admin account. Without Supabase nobody can obtain admin clearance, which is the safe default.

## 5. Start everything

```bash
mise run dev
```

This starts two processes:

- the gateway API on http://localhost:8000
- the web client on http://localhost:3000

Wait until the output shows Nuxt listening on port 3000. Leave this terminal running.

## 6. Explore the main menu and pick a level

Open http://localhost:3000. You are signed in as an anonymous player.

- The left column shows the main menu: **Play Game**, **Sign in / Create account** and **Settings**.
- The right column displays the **Leaderboard** for `Easy`, `Medium` and `Hard`.
- Click **Play Game** to see the level cards:
  - **Level 1 (`Easy`): Public Helpdesk**: classify prompts; the final node is the **Help Desk**.
  - **Level 2 (`Medium`)**: protect a modern AI agent (the **Protected Agent**).
  - **Level 3 (`Hard`)**: protect a budget model that is easier to trick.
- Click **Play** on **Level 1** to open `/game?level=easy`.

## 7. Build and wire a defence board

On `/game`:

1. The canvas starts with two locked nodes: **Input** and the final node. You
   must place at least one tool node between them.
2. Drag **Word filter** and **Quick screen** from the **Tools** panel onto the canvas.
3. Wire them by dragging from a port to the next node's `IN` port, for example
   Input → Word filter → Quick screen → Help Desk (from `SAFE`). An unwired
   output, and every block decision, stops the prompt.
4. Double-click **Word filter** to toggle its rule groups or add blocked phrases.
5. Optional: place an **ML filter**, upload a `.csv` (`text,label`), pick an
   algorithm and click **Train model**.

## 8. Run the wave

1. Click **Run wave**. The engine runs every prompt in the level's wave through
   your board and the **Run results** modal opens with your stars and score.
2. Click **Show breakdown** for the points, latency and cost, and the
   confusion matrix. Click a matrix cell to see which prompts landed there.
3. The header keeps your **High Score** and its stars for this visit. Sign in to
   save your board and record scores on the leaderboard.

## 9. Inspect the API and admin console

- **Interactive API docs:** with `mise run dev` (development mode), open
  http://localhost:8000/api/v1/docs to try `GET /api/v1/game/levels` or
  `POST /api/v1/game/run`.
- **Admin console:** if you created an admin with `mise run admin:create`, open
  http://localhost:3000/_console and sign in with that email and password to see score stats and the
  leaderboard, and to clear the scoreboard.

## 10. Stop the game

Press `Ctrl+C` in the terminal running `mise run dev`.

## Next steps

- [Configure LLM providers](../how-to/configure-llm-providers.md) runs the Medium and Hard agents on real models.
- [Architecture](../explanation/architecture.md) explains how the pieces fit together.
- [Tutorial 3: Your first spec-driven change](03-your-first-spec-driven-change.md) walks through changing the game the way this repo requires.
