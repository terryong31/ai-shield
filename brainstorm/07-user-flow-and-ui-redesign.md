# 07. User Flow and UI Redesign (`ai-shield`)

## 1. Core Principles of This Redesign

1. **Project Name:** Everything is branded as **`ai-shield`**.
2. **Less Text, More Game:** Strip away long paragraphs, explanations, and clutter. Use short labels (1 to 3 words), numbers, and visual node states.
3. **Permanent Anchor Nodes:**
   - Every board has 3 locked anchor nodes that **cannot be deleted**:
     1. **Input** (`incoming`) on the left.
     2. **Safe** (in Level 1 `easy`) or **Assistant** (in Level 2 `medium` and Level 3 `hard`) on the top right.
     3. **Blocked** (`blocked`) on the bottom right.
   - A starter board begins with only the 3 anchor nodes (`Input`, `Safe`/`Assistant`, `Blocked`) and **no pre-connected bypass wire**. The player must place at least one tool node from the left `Tools` panel in between `Input` and the destination nodes (`Safe`/`Assistant` and `Blocked`) before running a wave.
4. **Double-Click Node Modals (No Right Panel):**
   - The right-hand inspector panel is removed so the canvas gets maximum space.
   - Double-clicking any tool node opens a modal (`UModal`) to configure its settings, outgoing wires, or delete it.
   - Double-clicking `Input`, `Safe`/`Assistant`, or `Blocked` opens a modal showing the wave messages that passed through or landed in that node.
   - `Safe`/`Assistant` and `Blocked` display live message counters directly inside the node card on the canvas (for example, `Safe: 3` / `Leaked: 0` and `Blocked: 3` / `False alarm: 0`).
5. **Hidden Admin Console (`/_console`) with Supabase Auth + `UAuthForm`:**
   - Zero links or references to `/_console` exist anywhere in the public client UI (`/`, `/game`, layouts, or modals).
   - Visiting `/_console` directly shows a login screen built with Nuxt UI `<UAuthForm>` (`email` and `password` fields) backed by Supabase Auth (`sign_in_with_password` on the gateway, with local passphrase fallback when Supabase is not configured).

---

## 2. Page-by-Page User Flow & Wireframes

### Page 1: Landing Page / Game Main Menu (`/`)

A non-scrolling `100dvh` game main menu split into two columns:

```text
+----------------------------------------------------------------------------------+
|                                                                                  |
|   ai-shield                                 LEADERBOARD     [Easy] [Med] [Hard]  |
|   Defend the system.                                                             |
|                                             +----------------------------------+ |
|   +----------------------------+            | #  PLAYER      SCORE   MS    COST| |
|   |  PLAY GAME                 |            | 1  alex        9,420   14ms  $0  | |
|   +----------------------------+            | 2  sam         8,810   42ms  $0  | |
|                                             | 3  kai         7,950   95ms  $0  | |
|   +----------------------------+            +----------------------------------+ |
|   |  SETTINGS                  |                                                 |
|   +----------------------------+                                                 |
|                                                                                  |
+----------------------------------------------------------------------------------+
```

- **Left Column (Main Menu):**
  - Title: `ai-shield`
  - **Play Game** button: toggles/opens the **Choose Difficulty** view (`Easy`, `Medium`, `Hard`).
  - **Settings** button: opens the BYOD Model Settings modal (`offline`, `groq`, `openai`, `ollama`, `custom`).
- **Choose Difficulty Modal / View (when clicking Play Game):**
  - Displays the 3 difficulties (`Easy`, `Medium`, `Hard`).
  - Each card shows:
    - Difficulty badge (`Easy`, `Medium`, `Hard`) and level name
    - Completion badge: `Solved` or `Unsolved`
    - Player's personal best score (`Best: 9,420` or `Best: 0`)
    - Clicking a card navigates to `/game?level=easy|medium|hard`.
- **Right Column (Leaderboard):**
  - Tabs/buttons to filter by `Easy`, `Medium`, or `Hard`.
  - Clean table of top runs for the selected difficulty.

---

### Page 2: Game Screen (`/game`)

Two compact top bars, a narrow left `Tools` panel, and a full-width interactive Vue Flow canvas (no bottom bar, no right panel):

```text
+----------------------------------------------------------------------------------+
| [<- Back]  Level 1: Public Helpdesk               Difficulty: Easy | Score: 9420 |
+----------------------------------------------------------------------------------+
| [Run wave]  [Reset]   |  [Test message input........................] [Test]     |
+---------------+------------------------------------------------------------------+
| TOOLS         |                                                                  |
|               |                                            +------------------+  |
| +-----------+ |   +---------------+                        | SAFE (or ASST)   |  |
| | Cleaner   | |   | INPUT         |                        | Allowed: 3       |  |
| +-----------+ |   | 6 messages    o---+                    | Leaked:  0       |  |
| | Word filt | |   +---------------+   |   +------------+   +------------------+  |
| +-----------+ |                       +-->o ML Filter  o                         |
| | ML filter | |                           | (LogReg)   |                         |
| +-----------+ |                           +------------+   +------------------+  |
| | Quick scr | |                                            | BLOCKED          |  |
| +-----------+ |                                            | Caught: 3        |  |
| | Safety    | |   (Double-click any node for settings)     | False alarm: 0   |  |
| +-----------+ |                                            +------------------+  |
| | Agent rev | |                                                                  |
| +-----------+ |                                                                  |
| | Tool filt | |                                                                  |
| +-----------+ |                                                                  |
+---------------+------------------------------------------------------------------+
```

- **Top Nav 1 (Header Bar):**
  - **Left:** `Back` button (`i-lucide-arrow-left`) + Level Name (`Level 1: Public Helpdesk`).
    - Clicking `Back` opens a confirmation modal:
      `"Are you sure you want to quit? your progress will not be saved"`
      with `Cancel` and `Quit` buttons. Confirming destroys current board/wave state and returns to `/`.
  - **Right:** `Difficulty` badge (`Easy` / `Medium` / `Hard`), `Current Score` (`Score: 0` or wave score), and `Save score` button when a wave has been scored.
- **Top Nav 2 (Action Bar — replaces bottom nav):**
  - **Left:** `Run wave` button, `Reset` button, and compact wave stats (`Latency`, `Cost`, `Grade`) when available.
  - **Right:** Single-line custom test input + `Test` button to test one message through the board.
- **Left Panel (`Tools`):**
  - Title: `Tools` (no subtitle or description).
  - Compact tool buttons to drop onto the canvas:
    1. `Text cleaner` (`text_cleaner`)
    2. `Word filter` (`word_filter`)
    3. `ML filter` (`ml_classifier`) — trainable scikit-learn classifier with custom dataset upload and algorithm picker (`Logistic Regression`, `Linear SVM`, `Naive Bayes`, `Random Forest`)
    4. `Quick screen` (`quick_screen`) — pretrained TF-IDF baseline classifier
    5. `Safety check` (`safety_check`) — jailbreak & policy check
    6. `Agent review` (`agent_review`) — dual-agent Analyst + Warden debate
    7. `Tool filter` (`tool_filter`) — blocks dangerous tool calls
- **Canvas & Nodes:**
  - `Input`, `Safe` (Level 1) / `Assistant` (Levels 2 & 3), and `Blocked` are locked (`deletable: false`).
  - `Safe`/`Assistant` node displays how many messages reached it (`Safe: X` and `Leaked: Y`).
  - `Blocked` node displays how many messages were blocked (`Blocked: X` and `False alarm: Y`).
  - **Double-clicking any node** opens a `<UModal>`:
    - For `ML filter`: choose algorithm (`logistic_regression`, `linear_svm`, `naive_bayes`, `random_forest`), upload a `.csv` or `.jsonl` dataset (`text,label`), view sample count, adjust threshold, and wire outgoing handles (`safe`, `unclear`, `block`).
    - For `Word filter`: edit blocked phrases & regex patterns, and wire handles.
    - For other tool nodes: adjust threshold (if applicable), wire outgoing handles, or delete node.
    - For `Input`, `Safe`/`Assistant`, or `Blocked`: inspect the messages that landed there during the last wave.

---

### Page 3: Admin Console (`/_console`)

- Completely hidden from the public client UI (no links or buttons pointing to `/_console`).
- When not signed in, `/_console` renders a centered login card using Nuxt UI `<UAuthForm>`:
  - Fields: `email` (`type: 'email'`) and `password` (`type: 'password'`).
  - Authenticates against Supabase Auth (`supabase.auth.sign_in_with_password`) via the gateway `/api/v1/clearance` endpoint (with local admin passphrase fallback when Supabase is not configured in local dev/test).
- Once signed in, the admin can view system stats, delete leaderboard records, inspect audit logs (`/_console/logs`), and view runtime settings (`/_console/settings`).

