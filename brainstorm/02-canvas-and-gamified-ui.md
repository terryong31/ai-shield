# 02 — Canvas Architecture & Gamified UI Design

> Built strictly with **Nuxt 4**, **Nuxt UI (`@nuxt/ui`)**, and **Vue Flow (`@vue-flow/core`)** per project guidelines.

## 1. Full-Screen Tactical Workspace Layout (`/`)

Instead of the current 50/50 chat-and-static-diagram split, the home page (`/`) becomes a **full-viewport tactical canvas** with floating HUD overlays and collapsible drawers:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ [Shield Logo]  [Level 1: Public Helpdesk ▾]   [🏆 Best: 9,420]   [⚙️ BYOD/Admin] │ ← Top HUD Bar
├───────────────────┬──────────────────────────────────────────┬───────────────────┤
│ ARSENAL PALETTE   │             VUE FLOW CANVAS              │ LIVE TELEMETRY    │
│ (Drag to Canvas)  │                                          │ & WAVE INSPECTOR  │
│                   │   ┌─────────┐        ┌────────────┐      │                   │
│ [⚡ Regex Guard]  │   │ Ingress │──●────▶│ ML Filter  │      │ Core HP: ♥♥♥ (3/3)│
│  0.5ms | $0.00    │   └─────────┘        └──┬───┬───┬─┘      │ Blocked: 12 / 12  │
│                   │              safe ──────┘   │   └─block  │ False Pos: 0      │
│ [🧼 Sanitizer]    │                 ▼           ▼       ▼    │ Avg Speed: 14.2ms │
│  1.0ms | $0.00    │          ┌───────────┐ ┌────────┐ ┌────┐ │ Cost: $0.0030     │
│                   │          │Target AI  │ │Debate  │ │Sink│ │                   │
│ [🧠 ML Classifier]│          │Agent (HP) │ │Judge   │ │ 🗑️ │ │ [Wave Log Stream] │
│  4.0ms | $0.00    │          └─────┬─────┘ └────────┘ └────┘ │ ✓ #04 Benign 3ms  │
│                   │                ▼                         │ 🛡 #05 Blocked 4ms │
│ [⚖️ Debate Judge] │          ┌───────────┐                   │ ⚠ #06 Debating... │
│  950ms | $0.003   │          │RBAC Gate  │                   │                   │
│                   │          └───────────┘                   │ [Node Config]     │
│ [🔒 Tool RBAC]    │                                          │ Threshold: [0.65] │
├───────────────────┴──────────────────────────────────────────┴───────────────────┤
│ [▶ LAUNCH WAVE (20 Packets)]  [Speed: 1x | 2x | ⚡Max]  [🔄 Reset]  [🧪 Test Prompt]│ ← Bottom Action Dock
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. What Goes Inside the Vue Flow Canvas?

### A. Interactive Node Cards (`NodeContainer.vue` Evolved)
Every node on the canvas displays real-time tactical badges so the player can read their architecture at a glance:
1. **Header Bar:** Icon + Node Title + Layer Badge (e.g., `L1 EDGE`, `L2 ML`, `L4 LLM`) + Delete button (for placeable nodes).
2. **Cost & Speed Chips:** Always visible mini-badges (`⚡ 4ms` | `💲 $0.00`) so players see the trade-off right on the node.
3. **Live Per-Node Counters (During Wave):**
   - Mini pill showing how many packets passed through this node (`Processed: 18 | Blocked: 4`).
   - Cumulative latency/cost contributed by this specific node.
4. **Typed Output Handles (Color-Coded Ports):**
   - **Green Handle (`safe` / `pass`):** Connects to `Target AI Agent` or next check.
   - **Amber Handle (`suspicious` / `escalate`):** Connects to heavier inspection (`DualAgentNode`).
   - **Red Handle (`malicious` / `block`):** Connects to `OblivionNode` (Blocked sink).
5. **Inline Quick-Tune Control:**
   - E.g., on `MLNode`: a compact dual-threshold slider (`0.30` / `0.75`) directly on the node or in the selection popover.

### B. Animated Traffic Packets Along Edges
Using Vue Flow custom edges (`CustomPacketEdge.vue`) with SVG `<circle>` / `<g>` following `getBezierPath`:
- When a wave runs, each request spawns a glowing token that travels from `UserNode` through the connected edges.
- **Visual Feedback on Impact:**
  - **Blocked at Oblivion:** Satisfying emerald/cyan shield pulse (`+500 pts` floating badge).
  - **Legitimate Query Reaches Agent:** Smooth green check pulse (`200 OK`).
  - **False Positive (Legitimate Query sent to Oblivion):** Yellow warning flash (`SLA PENALTY -300 pts`).
  - **Security Breach (Attack Reaches Agent or Executes Forbidden Tool):** Red screen-edge vignette pulse, Target Agent HP bar drops by 1 heart, and an alarm badge shows the leaked secret (`BREACH: System Prompt Exfiltrated!`).

### C. Target AI Agent "Vault" Node (`AgentNode.vue`)
- Styled like a high-value server core / vault.
- Shows **Protected Secrets** inside the vault (e.g., `🔑 PROD_DB_URI`, `📄 CEO_Salary.pdf`).
- Shows **Integrity Hearts / Shield Bar** (`3 / 3`).
- Connects downstream to **Prod Toolbox (`ToolboxNode.vue`)** where sensitive tools (`query_db`, `send_wire`, `read_handbook`) live.

---

## 3. Gamified HUD Components (Using Nuxt UI)

| Component | Nuxt UI Primitives | Purpose |
| :--- | :--- | :--- |
| **Level Selector & Mission Briefing** | `UModal`, `UBadge`, `UCard`, `UTabs` | Explains the scenario, threat types in the upcoming wave, and Bronze/Silver/Gold target thresholds. |
| **Arsenal Sidebar** | `UCard`, `UTooltip`, HTML5 Drag-and-Drop (`@dragstart`, `@drop`) | Categorized list of defense nodes with cost/latency stats and locked/unlocked state per level. |
| **Live Telemetry HUD** | `UProgress`, `UBadge`, `UScrollArea` | Live scoreboard gauges (Security %, False Positive %, P95 Latency ms, Cost $) + clickable packet log. |
| **Wave Victory / Defeat Modal** | `UModal`, `UButton`, `UTable` | Shows animated score tally, Gold/Silver/Bronze medal, breakdown against best record, and name input for the Leaderboard. |
| **Custom Attack Sandbox ("Test My Defense")** | `USlideover` or bottom input bar | Lets the player type their *own* custom prompt injection at any time and watch it traverse their custom graph! |

---

## 4. Repurposing `/dashboard` → Admin Console & Telemetry Lab

Rather than deleting `/dashboard` completely, we turn it into the **Security Operations & Leaderboard Console**:
- **`/dashboard` (Leaderboard & Level Records):** High scores per level, saved winning graph blueprints (click to load a winning graph back onto the canvas!), and global telemetry.
- **`/dashboard/logs` (Audit & Packet Replay):** The existing SQLite audit log table—players or instructors can inspect every historical run, filter by `BREACHED` or `FALSE_POSITIVE`, and view the full dual-agent debate transcript.
- **`/dashboard/settings` (BYOD & Engine Config):** Configure execution mode:
  1. **Simulation / Offline Mode (Default):** Uses pre-computed embeddings/classifier + deterministic LLM judge fixtures so anyone can play at 60fps with zero API keys.
  2. **Live BYOD Mode (OpenAI / Anthropic / Gemini / Local Ollama):** Runs the actual player-built graph against live LLMs and the real `shield_engine` pipeline!

