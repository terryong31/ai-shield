# AGENTS.md: apps/web

The demo client. Root rules in [../../AGENTS.md](../../AGENTS.md) apply; these add to them.

## Map

| Path | Responsibility |
| --- | --- |
| `app/composables/useShieldApi.ts` | The only backend client (fetch + NDJSON stream + game endpoints) |
| `app/composables/useByodSecrets.ts` | In-memory BYOD API keys (`openai_api_key`, `groq_api_key`, `base_url`) |
| `app/utils/gameBoard.ts` | Pure board graph builder, node catalog, hop trace folding, and console access guard |
| `app/utils/chatStream.ts` | Pure NDJSON parsing + event reducer (spec 0008), unit-tested |
| `app/types/api.gen.ts` | **Generated** from the contract. Never edit; run `mise run contract` |
| `app/types/api.ts` | Friendly aliases over the generated types |
| `app/components/workflow/` | Vue Flow nodes (`GameNode.vue`, pipeline visualisers) |
| `app/pages/index.vue` | Game main menu, level selector cards, BYOD settings modal, and leaderboard |
| `app/pages/game.vue` | Interactive node-based defence board, double-click node configuration modal, custom ML training |
| `app/pages/console/` | Guarded `/_console` admin console (`UAuthForm` login, telemetry, audit log, settings) |

## Rules

- UI: use **Nuxt 4, Nuxt UI and Vue Flow components only**. Style with Nuxt UI
  semantic tokens (`text-muted`, `bg-elevated`, `border-default`), not raw
  palette colours, unless you are extending an existing node style. When
  unsure about a component API, consult the Nuxt UI docs or MCP server.
- Data: only through `useShieldApi()`. No Supabase or other data clients, and no secrets in `runtimeConfig.public`.
- Put logic worth testing in `app/utils/` as pure functions, and test it in `test/*.test.ts` with spec IDs in the test names.
- No `any`. Type Vue Flow refs as `Ref<Node[]>` (see `WorkflowVisualizer.vue`).
- Follow Nuxt UI writing standard. Check for latest documentation at https://ui.nuxt.com/ . For componenets check https://ui.nuxt.com/docs/components

Also please use UEmpty for empty states, and USplitter for resizable layouts.

Bad code example:
```js
<UModal>
  <template #content>
  <!-- header  -->
  <div>
  Something here
  </div>
  <!-- body  -->
  <div>
  Something here
  </div>
  <!-- footer  -->
  <div>
  Something here
  </div>
</UModal>
```
Good code example:
```js
<UModal>
  <template #header>
  Something here
  </template>

  <template #body>
  Something here
  </template>

  <template #footer>
  Something here
  </template>
</UModal>
```

## Commands

```bash
mise run web:dev
mise run test:web
bun run --cwd apps/web lint:fix
mise run typecheck:web
```
