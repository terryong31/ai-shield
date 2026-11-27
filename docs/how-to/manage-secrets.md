# Manage secrets (Infisical)

[Infisical](https://infisical.com) is the secrets manager of this project. The mise tasks read
secrets from Infisical when they start a process. Do not put secrets in the repository.

`.infisical.json` at the repository root connects the folder to the Infisical project. It contains
the project id and the default environment (`dev`). It contains no secret, and it is committed.

## Where each variable is

| Environment | Path | Used by | Variables |
| --- | --- | --- | --- |
| `dev` | `/api` | `mise run api:dev`, `up`, `stripe:listen` | `APP_ENV`, `CORS_ORIGINS`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, `LOG_LEVEL`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `TYPESAFE_API_KEY`, `WEB_BASE_URL` |
| `dev` | `/web` | `mise run web:dev` | `NUXT_API_PROXY_TARGET`, `NUXT_CLIENT_IP_HEADER`, `NUXT_PUBLIC_SITE_URL` |
| `prod` | `/api` | The API in production, `admin:remote:*`, `stripe:events` | The `dev` variables, and `MODEL_SIGNING_KEY`, `REDIS_URL`, `SUPABASE_URL`, `SUPABASE_KEY`, `TRUSTED_CLIENT_IP_HEADER`, `TRUSTED_PROXY_SECRET` |
| `prod` | `/web` | The web client in production | The `dev` variables, and `NUXT_API_PROXY_SECRET` |

The meaning of each variable is in [Configuration](../reference/configuration.md).

**Do not put `SUPABASE_URL` or `SUPABASE_KEY` in `dev /api`.** `scripts/local_env.py` reads the
local values from `supabase status`. If you set them in `dev`, local development uses that database.

## Set up your computer

1. Run `mise install`. It installs the pinned Infisical CLI.
2. Ask the owner for access to the Infisical project.
3. Sign in one time:

   ```bash
   infisical login
   ```

4. Start the game:

   ```bash
   mise run dev
   ```

## Add or change a secret

```bash
infisical secrets set NAME=value --env=dev --path=/api
```

Do the same for `prod` when production needs it. A command with a value stays in your shell history.
To keep the value out of the history, send it through standard input:

```bash
read -rs V && printf 'NAME=%s\n' "$V" | infisical secrets set --file=/dev/stdin --env=dev --path=/api; unset V
```

Then:

1. Add the variable to [Configuration](../reference/configuration.md) and to the `.env.example` file.
2. Restart the process. A running process does not see the change.
3. Production reads its variables from Vercel. Make sure that the value arrives in the Vercel
   project, then deploy again.

To see names without values, use the Infisical dashboard. `infisical secrets` prints the values.

## Precedence

1. The process environment, which includes the values from `infisical run`
2. `apps/api/.env`, if the file exists
3. The defaults in `settings.py`

`apps/api/.env` is optional and git-ignored. Use it for local overrides only.

## Work without access to Infisical

`mise run dev` (and `api:dev`, `web:dev`) works without Infisical (spec 0055). The tasks run
through `scripts/with_secrets.py`. When the Infisical CLI is missing or not signed in, it shows a
short notice and starts the command directly, so the apps read only their `.env` files:

```bash
mise run dev
```

To set optional local values, copy `apps/api/.env.example` to `apps/api/.env` and
`apps/web/.env.example` to `apps/web/.env`. The `up` task still needs an Infisical session.

The game works without provider keys. See
[Configure LLM providers](configure-llm-providers.md). CI and the tests do not use Infisical.

## If a secret leaks

1. Make a new key at the provider (Stripe, Google, Groq, Supabase).
2. Replace the value in Infisical, in each environment that uses it, and deploy.
3. Revoke the old key.
4. If the secret was in a commit, tell the owner. A new commit does not remove it from the history.

gitleaks scans each commit and the full history
([Work with CI and the git hooks](work-with-ci-and-git-hooks.md)).

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `infisical: command not found` | Run `mise install`, and activate mise in your shell |
| The task asks you to sign in | The session ended. Run `infisical login` |
| `403` from Infisical | Your account has no access to this project or environment |
| `Missing required configuration: STRIPE_WEBHOOK_SECRET` | `STRIPE_SECRET_KEY` is set without its webhook secret. Set both, or remove both |
