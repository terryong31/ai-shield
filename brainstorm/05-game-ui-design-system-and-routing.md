# 05 — Web Game UI Design Standard & Route Architecture

> **Purpose:** A structured, repeatable UI/UX framework for web-based simulation & logic games (inspired by *while True: learn()*, *Shapez*, *Screeps*, and *Lakera Gandalf*), built 100% on **Nuxt 4 + Nuxt UI Semantic Tokens + Vue Flow**.

---

## 1. Site Map & Route Architecture

| Route URL | File Path in `apps/web/app/pages/` | Access Level | Purpose |
| :--- | :--- | :--- | :--- |
| **`/`** | `pages/index.vue` | Public | **Game Landing Page:** High-impact hero, "How to Play" 3-step visual explainer, Level Select preview cards (Easy / Medium / Hard), Top 5 Hall of Fame Scoreboard, and primary `Play Now` CTA to `/game`. |
| **`/game`** | `pages/game.vue` | Public | **The Defender Workbench (Main Game):** Full-viewport Vue Flow canvas with peripheral HUD bars, Arsenal node dock, Wave Simulation runner, Custom Prompt Red-Team bar, and BYOD drawer. |
| **`/_console`** | `pages/console/index.vue`<br>*(with `definePageMeta({ path: '/_console', middleware: 'admin' })`)* | **Site Admin Only** | **Admin Command Center:** Locked behind the `HttpOnly` clearance session (`spec 0012`). Normal players cannot access it. Used to manage the Leaderboard, inspect full Audit Traces, and manage/seed Level Waves. |
| **`/_console/logs`** | `pages/console/logs.vue`<br>*(path: `/_console/logs`)* | **Site Admin Only** | Deep-dive packet audit log & reviewer feedback (migrated from `/dashboard/logs`). |
| **`/_console/settings`** | `pages/console/settings.vue`<br>*(path: `/_console/settings`)* | **Site Admin Only** | Site-wide guard thresholds, clearance session controls, and scoreboard reset. |

> [!NOTE]
> **Why `pages/console/` with `path: '/_console'`?**
> In Nuxt 4, files or folders named `_console` starting with an underscore `_` are ignored by the router as private partials. Placing the files in `app/pages/console/` with `definePageMeta({ path: '/_console', middleware: ['admin'] })` serves the exact `/_console` URL while keeping Nuxt routing clean.

### How `/_console` Admin Protection Works
We reuse the existing hardened `HttpOnly` session cookie (`POST /api/v1/clearance` from `spec 0012`):
1. When a user visits `/_console`, the `admin` route middleware checks `GET /api/v1/clearance`.
2. If `granted === false`, normal users see an **Admin Clearance Gate** (`UCard` modal/screen asking for the site admin passphrase) or are redirected back to `/`.
3. Only a user who authenticates with the server's `SECURE_PASSPHRASE` receives the `HttpOnly` cookie and enters `/_console`.

---

## 2. The "Tactical Instrument Panel" Game UI Framework

In simulation and workflow games (*while True: learn()*, *Shapez*, *Factorio*), **the UI is the game**. Players don't control a character; they operate an instrument panel. Follow these **5 Core Rules** so the UI always looks cohesive and professional without custom CSS hacks:

### Rule 1: The "90% Canvas, 10% Chrome" Spatial Law
Never trap a game canvas inside nested cards or padded containers.
- **Layer 0 (Base Canvas):** `VueFlow` fills `100vw x 100vh` (`bg-default`).
- **Layer 1 (Diegetic World UI):** Node cards, handle badges, and animated packets live *inside* the canvas coordinate space.
- **Layer 2 (Peripheral HUD Docks):** Pinned strictly to the edges using `bg-elevated/90 backdrop-blur` and `border-default`:
  - **Top Edge (`h-14`):** Mission Status, Level Selector, Core Integrity Hearts, Running Score, Latency & Cost gauges.
  - **Left Edge (`w-64` collapsible):** **Defense Arsenal** (draggable node cards grouped by layer).
  - **Right Edge (`w-80` collapsible):** **Wave Telemetry & Node Inspector** (live packet feed + selected node settings).
  - **Bottom Edge (`h-16`):** **Simulation Transport Bar** (`Launch Wave`, `1x / 2x / Instant`, `Reset`, and `Test Custom Prompt` popover).
- **Layer 3 (Modals):** Level Briefing, Wave Victory/Defeat Tally, Leaderboard, and BYOD Settings (`UModal` / `USlideover`).

### Rule 2: Strict Semantic Color Language (Zero Raw Palette Classes)
Every color on screen has **one exact gameplay meaning**, mapped to Nuxt UI semantic tokens (satisfying `WEB-UI-001`):

| Gameplay Concept | Nuxt UI Color Token | Visual Icon | Where It Appears |
| :--- | :--- | :--- | :--- |
| **Safe / Passed / Legitimate User** | `color="success"` | `i-lucide-shield-check` | Safe output handle, legitimate packet, 100% SLA badge |
| **Suspicious / Escalated / Latency Warning** | `color="warning"` | `i-lucide-triangle-alert` | Uncertain output handle, Dual-Agent Debate active state, False Positive warning |
| **Malicious Attack / Blocked / Breach** | `color="error"` *(badges/status)* | `i-lucide-Flame` / `i-lucide-skull` | Attack packet, Breach alert, Oblivion sink |
| **System / Logic / Speed / Cost** | `color="primary"` | `i-lucide-cpu` / `i-lucide-zap` | Active node border, selected wire, primary CTA buttons |
| **Locked / Idle / Inactive** | `color="neutral"` | `i-lucide-lock` | Unplaced arsenal nodes, idle wires, background grid |

### Rule 3: Typography Pairing (UI Sans + Tactical Monospace)
Simulation games look sharp because **labels use Sans-Serif** while **numbers use Monospace** (`tabular-nums`):
- **Headers & Labels:** Default UI sans (`font-semibold tracking-tight text-highlighted`).
- **Telemetry Numbers (Score, ms, $ Cost, Thresholds):** Always apply `font-mono tabular-nums` so numbers never jitter horizontally as they tick up during a wave!

### Rule 4: The "3-Second Readability" Node Card Standard
Every node on the canvas (`NodeContainer.vue`) follows an identical 3-tier anatomy:
```
┌──────────────────────────────────────────┐
│ [Icon] ML CLASSIFIER         [L2] [×]    │ ← Tier 1: Identity & Layer Badge (`bg-elevated`)
├──────────────────────────────────────────┤
│  ⚡ 3.8 ms     💲 $0.000     📊 14 hits  │ ← Tier 2: Monospace Telemetry Pills (`bg-default`)
│  Threshold: 0.30 — 0.75                  │
├──────────────────────────────────────────┤
│ ● in                        safe ●       │ ← Tier 3: Clearly Labeled IO Ports
│                       suspicious ●       │
│                            block ●       │
└──────────────────────────────────────────┘
```

### Rule 5: The Micro-Feedback Triad ("Game Juice" Within Design Hygiene)
To make a web app feel like a *game* (while passing `WEB-UI-003` — no `animate-pulse` or raw `shadow-[...]`):
1. **State Transitions:** Nodes shift border tokens (`border-default` → `border-primary` when active) with `transition-colors duration-200`.
2. **Animated SVG Edges:** Vue Flow edges set `animated: true` when a packet traverses them, plus a moving SVG `<circle>` token along the edge path.
3. **Score Tally & Medal Reveal:** When a wave ends, the Victory Modal uses `UProgress` bars for the 4 score dimensions (`Defense`, `UX / False Positives`, `Speed`, `Cost`) and awards a `Bronze`, `Silver`, or `Gold` `UBadge`.

---

## 3. Page-by-Page Blueprint

### Page 1: Landing Page (`/`)
Designed like modern developer games (*Lakera Gandalf*, *Elevator Saga*, *CSS Grid Garden*):
1. **Top Navbar:** Logo + `Play Campaign (/game)` + `Leaderboard` + subtle `Admin (/_console)` icon.
2. **Hero Section:**
   - **Tagline Badge:** `AI SECURITY ARCHITECTURE SIMULATOR`
   - **Headline:** *"Can You Defend Production AI Without Going Bankrupt?"*
   - **Subheadline:** *"Wire multi-layer guardrails. Block prompt injections. Let real users through. Compete for the fastest, cheapest defense."*
   - **Primary CTA:** `UButton size="xl" icon="i-lucide-play" to="/game"` → **"Enter Defense Lab"**
3. **Interactive 3-Card "Rules of Engagement" Strip:**
   - **1. Defend the Core:** Stop direct, encoded, and indirect prompt injections before they reach the Prod Agent.
   - **2. Don't Block Real Users:** False positives on legitimate queries tank your SLA score.
   - **3. Optimize Speed & Cost:** Layer $0 local ML filters in front of expensive LLM judges.
4. **Campaign Level Preview Grid (3 Cards):**
   - **Level 1: The Leaky Helpdesk** (`Easy` badge) — Click to launch `/game?level=level_1`
   - **Level 2: The HR Salary Heist** (`Medium` badge) — Click to launch `/game?level=level_2`
   - **Level 3: Zero-Day in Prod** (`Hard` badge) — Click to launch `/game?level=level_3`
5. **Global / Local Hall of Fame (`UTable`):**
   - Shows current top records per level (Player, Level, Medal, Score, Avg Speed ms, Wave Cost $).

### Page 2: The Game Workbench (`/game`)
- **Top HUD Bar:**
  - Back to `/` button + Level Selector dropdown (`USelectMenu` or `UDropdownMenu`).
  - **4 Live Metric Pills (`font-mono tabular-nums`):**
    - `Core HP: 3/3` (`color="success"` or `"error"`)
    - `Blocked: 0/8` (`color="primary"`)
    - `False Positives: 0` (`color="warning"`)
    - `Latency: 0.0ms | Cost: $0.0000` (`color="neutral"`)
  - Right actions: `Leaderboard` modal trigger + `BYOD Settings` slideover trigger.
- **Center Split / Canvas (`USplitter` or Floating Dock):**
  - Left: **Arsenal Palette** (drag nodes onto canvas) + **Level Briefing Summary**.
  - Center: **Interactive Vue Flow Canvas** (drag nodes, connect handles, delete edges/nodes, click node to configure thresholds).
  - Right: **Live Wave Feed** (every packet in the wave listed with status badge; click any packet to highlight its exact route on the canvas!).
- **Bottom Transport Bar:**
  - `Launch Wave` primary button + Speed selector (`1x`, `2x`, `Instant`) + `Reset Graph` button.
  - `Red-Team Custom Prompt` expandable input (`UInput` + `Send Test Packet` button) to fire your own prompt injection through your graph.

### Page 3: Admin Command Center (`/_console`)
- Accessible **only** when `useSecurityMode().isUnlocked` is `true` (backed by `GET /api/v1/clearance`).
- If locked: displays a centered `UCard` passphrase gate (`"Site Admin Clearance Required"`).
- When unlocked:
  - **Tab 1 — Overview & Telemetry:** Total waves played, breach rates, detector performance stats.
  - **Tab 2 — Scoreboard Moderation:** Manage leaderboard rows (delete anomalous entries, reset level records).
  - **Tab 3 — Audit Logs (`/_console/logs`):** Inspect every request trace and submit reviewer feedback (`false_positive` / `false_negative`).
  - **Tab 4 — Engine & Session Settings (`/_console/settings`):** Revoke clearance session, view default thresholds.

