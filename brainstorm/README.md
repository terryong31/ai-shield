# AI S.H.I.E.L.D. Game Refactor Brainstorm

An interactive node-based AI security game that teaches engineers how to design multi-layer defence pipelines against prompt injection.

## Why This Works

Most AI security games focus on writing a single attack prompt or a static system prompt. In real production systems, instructions alone always fail. Protecting an AI assistant is an architecture problem with three trade-offs:

1. **Protection and Accuracy:** Block prompt injections and unauthorized tool calls without blocking normal users (false alarms).
2. **Speed:** Keep response time in milliseconds so users do not wait.
3. **Cost:** Use free local filters first and send only unclear messages to slower, paid AI reviewers.

By turning the game page into an interactive board, players learn real defence architecture by placing checks, wiring branches, and testing their setup against waves of normal and harmful messages.

## Documents in This Folder

| File | Focus Area |
| :--- | :--- |
| [01-game-design-and-levels.md](file:///Users/terryong/Desktop/nuxt-projects/ai-shield/brainstorm/01-game-design-and-levels.md) | Core game loop, available checks, message types, levels (Easy, Medium, Hard), and scoring math. |
| [02-canvas-and-gamified-ui.md](file:///Users/terryong/Desktop/nuxt-projects/ai-shield/brainstorm/02-canvas-and-gamified-ui.md) | Board layout, node cards, message animations, controls, and admin console. |
| [03-system-architecture-and-byod.md](file:///Users/terryong/Desktop/nuxt-projects/ai-shield/brainstorm/03-system-architecture-and-byod.md) | Engine graph runner, live wave streaming, offline vs custom API key modes, and SQLite scoreboard. |
| [04-master-design-spec.md](file:///Users/terryong/Desktop/nuxt-projects/ai-shield/brainstorm/04-master-design-spec.md) | Consolidated specification with exact scoring formula, node handles, and implementation plan. |
| [05-game-ui-design-system-and-routing.md](file:///Users/terryong/Desktop/nuxt-projects/ai-shield/brainstorm/05-game-ui-design-system-and-routing.md) | Route structure (`/`, `/game`, `/_console` for site admin) and monochrome game interface rules. |
| [06-ui-and-copy-standard.md](file:///Users/terryong/Desktop/nuxt-projects/ai-shield/brainstorm/06-ui-and-copy-standard.md) | Anti-slop UI standard: monochrome high-contrast styling, plain English vocabulary, no emojis, no jargon, and no em-dashes. |
