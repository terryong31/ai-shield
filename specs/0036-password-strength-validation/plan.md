# 0036 — Password strength indicator, Change password, and Zod auth validation: implementation plan

- **Spec:** [spec.md](spec.md)

## Approach

1. **Web client (`apps/web/package.json`, `utils/playerAuth.ts`, `utils/account.ts`, `components/`, `pages/auth/{register,login}.vue`, `pages/settings.vue`)**:
   - Declare `"zod": "^4.6.7"` directly in `apps/web/package.json` (already resolved at `4.6.7` in the workspace).
   - Add `PASSWORD_REQUIREMENTS`, `checkPasswordStrength`, `passwordStrengthScore`, `passwordStrengthColor`, `passwordStrengthText`, `isStrongPassword`, `strongPasswordSchema`, `registerSchema`, `loginSchema`, and `passwordChangeSchema` in `apps/web/app/utils/playerAuth.ts`.
   - Extract a reusable `<PasswordStrengthInput>` component (or shared indicator snippet) using Nuxt UI's `<UInput>` with `#trailing` show/hide `<UButton>`, `<UProgress :color="color" :indicator="text" :model-value="score" :max="4" size="sm" />`, status paragraph (`id="password-strength"`), and the 4-item checklist (`i-lucide-circle-check` / `i-lucide-circle-x`), avoiding literal `color="error"` attributes per `WEB-UI-005`.
   - Wire `:schema="registerSchema"` and `<template #password-field="{ state }">` in `apps/web/app/pages/auth/register.vue`.
   - Wire `:schema="passwordChangeSchema"` and `<PasswordStrengthInput>` for `passwordForm.next` in `apps/web/app/pages/settings.vue`, and update `passwordChangeReady` in `apps/web/app/utils/account.ts` to require `isStrongPassword(form.next)`.
   - Wire `:schema="loginSchema"` to `<UAuthForm>` in `apps/web/app/pages/auth/login.vue`.
2. **Backend API (`apps/api/src/shield_api/schemas.py`, `apps/api/tests/`)**:
   - Extract a validated `StrongPassword` type/validator (`min_length=8, max_length=512`, digit + lowercase + uppercase) applied to `PlayerRegisterRequest.password` and `AccountPasswordRequest.new_password`.
   - Update `PlayerLoginRequest.password` to `Annotated[str, Field(min_length=8, max_length=512)]`.
   - Update weak test fixture passwords across `apps/api/tests/` (`test_clearance.py`, `test_game_agent_api.py`, `test_game_api.py`, `test_game_custom_api.py`, `test_game_levels_api.py`, `test_game_saves_api.py`, `test_player_confirmation.py`, `test_account_settings.py`) and `apps/web/test/accountSettings.test.ts`.
   - Regenerate `contracts/shield-api.openapi.json` and `apps/web/app/types/api.gen.ts` via `mise run contract`.

## Interfaces

```python
StrongPassword = Annotated[str, Field(min_length=8, max_length=512), AfterValidator(_validate_strong_password)]

class PlayerRegisterRequest(BaseModel):
    email: PlayerEmail
    password: StrongPassword
    player_name: Annotated[str, Field(min_length=1, max_length=64)] | None = None

class PlayerLoginRequest(BaseModel):
    email: PlayerEmail
    password: Annotated[str, Field(min_length=8, max_length=512)]

class AccountPasswordRequest(BaseModel):
    current_password: CurrentPassword
    new_password: StrongPassword
```

```ts
export const strongPasswordSchema: z.ZodString
export const registerSchema: z.ZodObject<...>
export const loginSchema: z.ZodObject<...>
export const passwordChangeSchema: z.ZodObject<...>
export function checkPasswordStrength(password: string): Array<{ met: boolean, text: string }>
export function isStrongPassword(password: string): boolean
```

## Boundaries check

- [ ] `packages/engine` untouched
- [ ] `apps/web` still talks to the backend only through the published OpenAPI contract
- [ ] Contract regenerated with `mise run contract`

## Alternatives considered

| Option | Why not |
| --- | --- |
| Validate only with manual `:validate` callbacks instead of Zod | Nuxt UI's `<UForm>` and `<UAuthForm>` natively integrate with Standard Schema (`zod`), and the owner explicitly requested Zod validation per Nuxt UI docs. |

## Risks and rollback

- Tightening `PlayerLoginRequest.password` to `min_length=8` assumes accounts comply with >= 8 chars on login (`test_account_settings.py` / existing login fixtures must be at least 8 chars, e.g. `"Password123"`).
- Declaring `"zod"` in `apps/web/package.json` requires confirmation per `AGENTS.md` ("Ask before: adding a dependency"), though `zod@4.6.7` is already installed in the lockfile as a transitive dependency of `@nuxt/ui`.
