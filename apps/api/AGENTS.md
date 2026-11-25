# AGENTS.md: apps/api

The game gateway. Root rules in [../../AGENTS.md](../../AGENTS.md) apply; these add to them.

## Map

| Path | Responsibility |
| --- | --- |
| `routers/` | HTTP mapping only: parse, call a service/engine, shape the response |
| `routers/game.py` | Levels, runs (quota, custom sandbox), saves, scores, ML training |
| `routers/auth.py` | Player sessions: anonymous, register, login, recover, upgrade, logout |
| `routers/clearance.py` | `POST/GET/DELETE /clearance`: the only route that sees an admin's password |
| `services/admins.py` | Admin check: Supabase Auth sign-in plus `app_metadata.role == "admin"` |
| `admin_cli.py` | `mise run admin:create` / `admin:revoke`: grant or remove the admin role |
| `services/clearance.py` | admin session cookie → `Clearance` (fail closed) |
| `services/sessions.py` | Admin clearance sessions (hashed tokens) and the failed-attempt limiter |
| `services/players.py` | Player accounts, sessions, daily quotas and saved boards |
| `services/scores.py` | `ScoreStore` protocol (leaderboard): Supabase (production/local), in-memory test double |
| `providers/` | Model adapters: Gemini (standard-tier agent) and the BYOK provider allowlist |
| `container.py` | Composition root; the only place that reads provider settings |
| `schemas.py` | Public contract (HTTP models) |

## Rules

- No detection logic here. If you are about to compare a score to a threshold,
  it belongs in `packages/engine`.
- Routers depend on `ContainerDep`; tests build a `Container` with fakes and
  call `create_app(container)`. Never patch module globals.
- Changing `schemas.py` changes the contract: run `mise run contract`, commit
  `contracts/shield-api.openapi.json` and `apps/web/app/types/api.gen.ts`.
- Stream errors are generic (`GENERIC_ERROR`); log details server-side with `logger.exception`.
- Never log or persist an admin's password or a raw session token. Store only the token's
  SHA-256 hash; audit metadata keeps only `clearance` (API-CLEAR-016).
- Admin is `app_metadata.role`, never `user_metadata` (users can write it).
- Demo tool risk labels are part of the security boundary (API-TOOLS-001).

## Commands

```bash
mise run api:dev            # http://localhost:8000/api/v1/docs
mise run test:api
```
