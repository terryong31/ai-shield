# Run the end-to-end tests

Playwright tests in `apps/web/e2e/` drive the real application in a browser. They use
only free checks, so a run does not call a paid model.

## Run against the local stack

1. Install the browser: `cd apps/web && bunx playwright install chromium`.
2. Start the stack: `mise run dev`.
3. Run the tests: `mise run test:e2e`.

The account test is skipped unless `E2E_EMAIL` and `E2E_PASSWORD` are set. Use a test
account with a confirmed email address. The test overwrites its saved board on `easy-2`.

## Run against a deployment

Set `E2E_BASE_URL` to the deployment URL. If the deployment is protected, also set
`VERCEL_AUTOMATION_BYPASS_SECRET`.

## Turn on the tests for preview deployments

The workflow `.github/workflows/e2e.yml` is off until you do these steps. It is advisory:
it is not part of `CI OK`.

1. Deploy a gateway for previews. Give it its own Supabase project and Redis. Do not use
   production data.
2. Add **Preview** environment variables to the web project in Vercel:
   `NUXT_API_PROXY_TARGET`, `NUXT_API_PROXY_SECRET`, `NUXT_CLIENT_IP_HEADER` and
   `NUXT_PUBLIC_SITE_URL`. Without them, the proxy answers `503`.
3. Make sure that BotID lets the tests through on previews. BotID can block an automated
   browser on the sign-in, anonymous-session and run routes. Do not weaken it in production.
4. In Vercel, open **Deployment Protection** and create a **Protection Bypass for
   Automation** secret. Keep the protection on.
5. Add the GitHub repository secret `VERCEL_AUTOMATION_BYPASS_SECRET`.
6. Create a test account in the preview Supabase project. Add the secrets `E2E_EMAIL` and
   `E2E_PASSWORD`. Do not use a real inbox: screenshots can show the address.
7. Set the repository variable `E2E_ENABLED` to `true`.

GitHub runs `deployment_status` workflows only after the file is on the default branch.

A failed run uploads traces and screenshots. `scripts/redact_traces.py` first removes
cookies, credential headers and the secret values. If it fails, nothing is uploaded.
