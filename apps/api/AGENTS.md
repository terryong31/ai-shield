# AGENTS.md: apps/api

The demo gateway. Root rules in [../../AGENTS.md](../../AGENTS.md) apply; these add to them.

## Map

| Path | Responsibility |
| --- | --- |
| `routers/` | HTTP mapping only: parse, call a service/engine, shape the response |
| `services/chat.py` | `/chat` flow: engine events → NDJSON events → demo assistant |
| `services/access.py` | session cookie → `Clearance`, mode → `ShieldConfig` |
| `services/sessions.py` | Clearance sessions (hashed tokens in SQLite) and the failed-attempt limiter |
| `routers/clearance.py` | `POST/GET/DELETE /clearance`: the only route that sees the passphrase |
| `services/audit.py` | `AuditLog` protocol: SQLite (default), Supabase, in-memory test double |
| `demo/` | The *protected application*: assistant, simulated tools, Gemini adapter |
| `container.py` | Composition root; the only place that reads provider settings |
| `schemas.py` | Public contract (HTTP models + `ChatEvent` union) |

## Rules

- No detection logic here. If you are about to compare a score to a threshold,
  it belongs in `packages/engine`.
- Routers depend on `ContainerDep`; tests build a `Container` with fakes and
  call `create_app(container)`. Never patch module globals.
- Changing `schemas.py` changes the contract: run `mise run contract`, commit
  `contracts/shield-api.openapi.json` and `apps/web/app/types/api.gen.ts`.
- Stream errors are generic (`GENERIC_ERROR`); log details server-side with `logger.exception`.
- Never log or persist the passphrase or a raw session token. Store only the token's
  SHA-256 hash; audit metadata keeps only `clearance` (API-CLEAR-003).
- Demo tool risk labels are part of the security boundary (API-TOOLS-001).

## Commands

```bash
mise run api:dev            # http://localhost:8000/api/v1/docs
mise run test:api
```
