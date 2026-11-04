# 06 - Anti-Slop UI and Plain English Standard

This document defines the visual and writing rules for the AI S.H.I.E.L.D. Defender game. Every screen, component, and text string must follow these rules so the product looks like a crafted engineering instrument (like *Mini Metro*, *Shenzhen I/O*, or *Teenage Engineering*), never like a generic AI template.

## 1. Visual Design Rules (How Not to Look Like Slop)

### Rule 1: High-Contrast Monochrome First
- **No purple-to-cyan gradients, neon glows, or glassmorphic blur cards.**
- Primary colour is stark black in light mode and stark white in dark mode (`WEB-UI-004`).
- Visual hierarchy comes from **weight, border style, fill density, and layout spacing**, not rainbow badges:
  - **Idle node:** Hairline dashed border (`border-dashed border-default`), dimmed label ("Idle").
  - **Running node:** Solid border (`border-default`), spinner icon, animated dashed wire into the node ("Running").
  - **Passed node:** Solid border (`border-default`), check icon ("Passed").
  - **Flagged / Unclear node:** Solid border, subtle diagonal hatch fill, alert icon ("Flagged").
  - **Blocked node:** High-contrast inverted fill (`bg-inverted text-inverted`), shield-x icon ("Blocked").
- **Red (`color="error"`) is reserved strictly for destructive buttons** (such as "Reset board", "Clear scores", or "Revoke admin access", per `WEB-UI-005`).

### Rule 2: Asymmetric Functional Layout (No 3-Column SaaS Grids)
- Do not build a generic SaaS marketing page with centered gradient text and three rounded feature cards.
- **Landing Page (`/`):** Built like a technical specification sheet and arcade level select board. Left column shows the title, rules, and "Start game" button; right column shows the live level records table and level cards with crisp `1px` borders.
- **Game Page (`/game`):** Full-screen grid canvas (`VueFlow`) framed by crisp `1px` structural bars (`border-default`):
  - **Top bar:** Level picker, live counters (Blocked, False alarms, Time per message, Cost), and button to open settings.
  - **Left panel:** Available checks you can drag onto the board.
  - **Center:** The board where you wire checks between incoming messages and the assistant.
  - **Right panel:** Incoming message list and settings for the selected check.
  - **Bottom bar:** "Run wave" button, speed toggle (`1x`, `2x`, `Max`), "Reset board", and a text box to test your own message.

### Rule 3: Typography with Purpose
- **Labels and prose:** Clean sans-serif with tight headings and generous line height for instructions.
- **Numbers, timers, costs, and scores:** Always monospace with aligned digits (`font-mono tabular-nums`). When a timer ticks from `4.2 ms` to `12.8 ms`, the layout must never shift horizontally.

### Rule 4: Zero Emojis
- Never use emojis anywhere in the UI, buttons, modals, logs, or documentation.
- Use simple 16px Lucide line icons (`UIcon`) paired with a clear text label.

---

## 2. Plain English Copywriting Rules

1. **No em-dashes (`--` or the long dash character).** Use periods, commas, colons, or parentheses instead.
2. **No sci-fi, military, or startup buzzwords.** Ban words like "Oblivion", "Arsenal", "Neutralized", "Tactical HUD", "Telemetry", "DAG Topology", "Adjudication", "Ingress", "Payload", "Deflector", "Supercharge", or "Next-gen".
3. **Short, everyday sentences in British/Malaysian English** (`colour`, `analyse`, `authorise`, `defence`). Explain what a check does so a first-time player understands it in two seconds.

### Approved Vocabulary Table

| Old / Jargon Term | Plain English Term Used in Game | Short Description on Card |
| :--- | :--- | :--- |
| `Ingress / UserNode` | **Incoming messages** | Customer messages and hidden attacks start here. |
| `Regex Guard / Heuristic` | **Word filter** | Blocks known attack phrases right away. Fast and free, but easy to trick. |
| `Input Sanitizer` | **Text cleanup** | Unpacks hidden text tricks and marks user text clearly before the next check. |
| `ML Classifier` | **Quick screen** | A small local model that scores how risky a message looks. Free and fast. |
| `Moderation Detector` | **Safety check** | Checks for harmful or abusive topics. |
| `Dual-Agent Debate Judge` | **Agent review** | Two AI reviewers (Analyst and Warden) read the message carefully. Very accurate, but slow and costs money. |
| `Target AI Agent` | **Assistant** | Answers customer questions using private company files and tools. Keep attacks out. |
| `Tool RBAC Gate` | **Tool filter** | Checks if the user has permission before the assistant can run sensitive tools. |
| `Oblivion Node` | **Blocked** | Harmful messages stop here safely. |
| `False Positive` | **False alarm** | A normal user message that your board blocked by mistake. Reduces your score. |
| `False Negative / Breach` | **Leaked** | An attack that slipped past your checks and reached the assistant. |
| `BYOD Mode` | **Model settings** | Run offline for free, or connect your own API key or local model. |
| `/_console` | **Admin console** | Site admin page to manage scores, review logs, and change access. |

