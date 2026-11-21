# 0041 — Same-origin API proxy: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

1. **Client:** `useShieldApi` and `useLeaderboard` use a shared constant
   `SHIELD_API_PREFIX = '/api/v1'` from `app/utils/apiPaths.ts` instead of
   `runtimeConfig.public.apiBaseUrl`. `credentials: 'include'` stays (harmless
   same-origin, keeps intent explicit).
2. **Proxy logic (pure, testable):** `apps/web/shared/utils/apiProxy.ts` exports
   `resolveUpstreamUrl(target, requestUrl)` and `proxyToGateway(request, target, fetchImpl)`.
   It works on web-standard `Request`/`Response`, so tests use a fake `fetch`
   and no network.
   It calls `fetchImpl(url, { method, headers, body, redirect: 'manual' })` and
   returns `new Response(upstream.body, …)` with filtered headers; multiple
   `Set-Cookie` values are appended separately (tests read them with
   `Headers.getSetCookie()`).
3. **Nitro route:** `apps/web/server/routes/api/v1/[...path].ts` converts the h3
   event with `toWebRequest(event)`, calls `proxyToGateway` with
   `useRuntimeConfig(event).apiProxyTarget`, and returns the `Response`. h3
   streams web `Response` bodies and splits `Set-Cookie`; this thin glue is not
   unit-tested and is checked manually with `mise run dev` (sign-in plus
   leaderboard stream) and after the first Vercel deploy.
4. **Composables:** WEB-PROXY-001/002 also assert, by reading source files as the
   existing UI tests do, that `app/` no longer reads `apiBaseUrl` and that
   `useLeaderboard.ts` uses `LEADERBOARD_STREAM_PATH`.
5. **Config:** `runtimeConfig.apiProxyTarget` (private, env `NUXT_API_PROXY_TARGET`,
   default `http://localhost:8000`); remove `runtimeConfig.public.apiBaseUrl`.
   Update `apps/web/Dockerfile` and `compose.yaml` (`NUXT_API_PROXY_TARGET=http://api:8000`).

## Interfaces

```ts
// app/utils/apiPaths.ts
export const SHIELD_API_PREFIX = '/api/v1'
export const LEADERBOARD_STREAM_PATH = `${SHIELD_API_PREFIX}/game/scores/stream`

// shared/utils/apiProxy.ts
export function resolveUpstreamUrl(target: string, requestUrl: string): URL | null
export function forwardableRequestHeaders(headers: Headers): Headers
export async function proxyToGateway(
  request: Request, target: string, fetchImpl?: typeof fetch
): Promise<Response>
```

Breaking (config only): `NUXT_PUBLIC_API_BASE_URL` is replaced by `NUXT_API_PROXY_TARGET`.

## Boundaries check

- [x] `packages/engine` untouched
- [x] `apps/web` still talks to the backend only through the published OpenAPI contract (the proxy is path-transparent)
- [ ] New configuration is documented in `docs/reference/configuration.md`, `docs/how-to/deploy.md`, ADR 0004 note

## Alternatives considered

| Option | Why not |
| --- | --- |
| `SameSite=None; Secure` cookies | Third-party cookies are blocked by Safari and restricted in Chrome; sign-in breaks for many players |
| Custom domain (`app.` / `api.` same site) | Needs a purchased domain; not available now. The proxy keeps working if one is added later |
| `routeRules: { '/api/v1/**': { proxy } }` | Target fixed at build time and no control over path escapes, header filtering or error bodies |
| Vercel `rewrites` in `vercel.json` | Ties local dev and Docker to different code paths; not testable in Vitest |

## Risks and rollback

- Extra hop adds latency to every API call (one server-to-server request).
- SSE through a Vercel function ends at max duration; `EventSource` reconnects.
- Vercel caps function request bodies (4.5 MB); API bodies are small JSON.
- `NUXT_API_PROXY_TARGET` must be set on the web project in Vercel; the default
  `http://localhost:8000` answers every call with `502`. Added to the deploy guide.
- Compose: `PUBLIC_API_URL` is replaced by an internal `NUXT_API_PROXY_TARGET=http://api:8000`;
  noted in `CHANGELOG.md`.
- Rollback: revert the commit (which restores `runtimeConfig.public.apiBaseUrl`)
  and set `NUXT_PUBLIC_API_BASE_URL` again.
