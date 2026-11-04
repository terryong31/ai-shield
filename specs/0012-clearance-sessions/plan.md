# 0012 — Clearance sessions: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

A new `services/sessions.py` owns the session store. A new
`routers/clearance.py` maps the three endpoints. `services/access.py` gains
`clearance_for(token)`, which replaces the passphrase path used by `/chat`
and `/screen`. Wiring happens only in `container.py`.

```
browser ──POST /clearance {passphrase}──▶ router ──verify (hmac)──▶ SessionStore.create()
        ◀── Set-Cookie: shield_session ──                          └─ sessions(token_hash, created_at, expires_at)
browser ──POST /chat (cookie)──▶ router ──SessionStore.lookup(hash)──▶ Clearance ──▶ engine
```

## Interfaces

```python
# services/sessions.py
class SessionStore(Protocol):
    async def create(self, ttl: timedelta) -> tuple[str, datetime]: ...   # (raw token, expires_at)
    async def lookup(self, token: str) -> datetime | None: ...            # expires_at if live
    async def revoke(self, token: str) -> None: ...

class SqliteSessionStore: ...      # table `sessions` in SQLITE_PATH
class InMemorySessionStore: ...    # test double

class AttemptLimiter: ...          # in-process sliding window per client address; also answers "failed recently?" for DENIED

# services/access.py
async def clearance_for(token: str | None, client: str, store: SessionStore, limiter: AttemptLimiter) -> Clearance
# live session → GRANTED; recent failure from `client` → DENIED; else NONE; store error → NONE (logged)

# schemas.py
class ClearanceRequest(BaseModel): passphrase: Annotated[str, Field(min_length=1, max_length=512)]
class ClearanceStatus(BaseModel): granted: bool; expires_at: datetime | None
# ChatRequest / ScreenRequest: `passphrase` removed (breaking)
```

SQLite table (created on open, like `SqliteAuditLog`):

```sql
create table if not exists sessions (
  token_hash text primary key,     -- sha256 hex of the raw token
  created_at text not null,
  expires_at text not null
);
```

This table is not mirrored to Supabase (a non-goal), so API-STORE-006, which
checks only `requests`, is unaffected.

## Web client changes (delivered with spec 0011, slice 1)

- `useShieldApi()` sends `credentials: 'include'` on `$fetch` and on the
  streaming `fetch`, and adds `getClearance`, `grantClearance` and
  `revokeClearance`.
- `useClearance()` holds only `ClearanceStatus`; it removes the legacy
  `localStorage` key on load (WEB-CLEAR-001).
- The "Admin access" dialog shows the expiry time, and a 401 or 429 inline
  on the form.

## Boundaries check

- [x] `packages/engine` untouched; the engine still sees only `Clearance`
- [x] Wiring only in `container.py`
- [x] Contract change is explicit: `mise run contract`, commit both generated files
- [x] New configuration documented in `docs/reference/configuration.md`
- [x] No new dependency (`secrets`, `hashlib`, `sqlite3` are stdlib)

## Alternatives considered

| Option | Why not |
| --- | --- |
| Keep sending the passphrase, but from `sessionStorage` | Still a plaintext secret that scripts can read, sent on every request |
| Signed stateless cookie (JWT or itsdangerous) | Cannot be revoked server-side without a deny-list; needs a new signing secret and possibly a dependency |
| Store the raw token | A leaked database would allow replay; hashing costs nothing |
| Sessions in Supabase too | A new migration and backend to keep in sync, for a single-instance demo |

## Risks and rollback

- **Cookie not sent in development** (Safari with `Secure` on `http://localhost`).
  Mitigation: `SESSION_COOKIE_SECURE=false` documented for local HTTP.
- **Breaking contract** for any script that sends `passphrase`. Mitigation:
  noted in `CHANGELOG.md` under *Changed* and in `docs/reference/http-api.md`.
  Pydantic ignores unknown fields, so old clients get `NONE` rather than an error.
- **Rollback:** revert the PR. The `sessions` table is inert without the code.
