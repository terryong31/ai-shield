# 0036 — Password strength indicator, Change password, and Zod auth validation

- **Status:** Implemented
- **Area:** API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-17
- **Related:** [0016-game-engine](../0016-game-engine/spec.md), [0025-account-settings](../0025-account-settings/spec.md), [0027-player-email-confirmation](../0027-player-email-confirmation/spec.md)

## Problem

1. `/auth/register`, `POST /api/v1/auth/register`, `/settings` Change password, and `POST /api/v1/auth/account/password` currently accept any 6-character password (`min_length=6`) with no strength requirements or live strength indicator.
2. `/auth/login` and `POST /api/v1/auth/login` lack Zod schema validation on the client (`z.email`, `min(8)`) and accept 1-character passwords on the server (`min_length=1`).

## Goals

- Enforce Nuxt UI's 4 password strength requirements (`https://ui.nuxt.com/docs/components/input#with-password-strength-indicator`) on both client (via Zod schemas) and server (`StrongPassword` in `schemas.py`) for **both** account registration (`/auth/register`, `POST /api/v1/auth/register`) and changing password (`/settings`, `POST /api/v1/auth/account/password`):
  1. At least 8 characters (`/.{8,}/`, up to 512 characters)
  2. At least 1 number (`/\d/`)
  3. At least 1 lowercase letter (`/[a-z]/`)
  4. At least 1 uppercase letter (`/[A-Z]/`)
- Render Nuxt UI's password strength indicator (`<UInput>` with `#trailing` show/hide `<UButton>`, `<UProgress :max="4">`, strength status text, and the 4-item requirements checklist with `i-lucide-circle-check` / `i-lucide-circle-x`) on `/auth/register` (`<UAuthForm>` `#password-field` slot) and `/settings` (Change password modal).
- Validate `/auth/login` and `POST /api/v1/auth/login` using Zod on the client (`z.email('Invalid email')`, `z.string('Password is required').min(8, 'Must be at least 8 characters')`) and matching rules on the server (`PlayerEmail`, `min_length=8`).

## Non-goals

- Requiring special characters beyond the 4 rules above.
- Modifying password-strength checks for delete/reset/change-email current-password confirmation prompts (those validate the player's existing password).

## Behaviour

### Client (`/auth/register`, `/settings`, `/auth/login`)

- Shared Zod schemas and strength helpers live in `apps/web/app/utils/playerAuth.ts`:
  - `strongPasswordSchema`: `z.string('Password is required')` enforcing `.min(8)` + regexes `/\d/`, `/[a-z]/`, `/[A-Z]/`.
  - `registerSchema`: `{ player_name, email: z.email('Invalid email'), password: strongPasswordSchema }`.
  - `loginSchema`: `{ email: z.email('Invalid email'), password: z.string('Password is required').min(8, 'Must be at least 8 characters') }`.
  - `passwordChangeSchema`: `{ current: z.string().min(1), next: strongPasswordSchema, confirm }` checking `next === confirm` and `next !== current`.
  - `checkPasswordStrength`, `passwordStrengthScore`, `passwordStrengthColor`, `passwordStrengthText`, `isStrongPassword`.
- `/auth/register` passes `:schema="registerSchema"` to `<UAuthForm>` and renders Nuxt UI's password strength indicator inside `<template #password-field="{ state }">`.
- `/settings` Change password `<UForm>` passes `:schema="passwordChangeSchema"`, renders Nuxt UI's password strength indicator on `New password` (`passwordForm.next`), and gates submit on `passwordChangeReady(passwordForm)` (`isStrongPassword(form.next)`).
- `/auth/login` passes `:schema="loginSchema"` to `<UAuthForm>`.

### Server (`apps/api/src/shield_api/schemas.py`)

| Schema / Field | Validation | Error response |
| --- | --- | --- |
| `PlayerRegisterRequest.password` (`POST /api/v1/auth/register`) | 8 to 512 chars, >= 1 digit (`[0-9]`), >= 1 lowercase (`[a-z]`), >= 1 uppercase (`[A-Z]`) | `422 Unprocessable Content` |
| `AccountPasswordRequest.new_password` (`POST /api/v1/auth/account/password`) | Same `StrongPassword` rules + differs from `current_password` | `422 Unprocessable Content` |
| `PlayerLoginRequest.email`, `.password` (`POST /api/v1/auth/login`) | `PlayerEmail`, `password` 8 to 512 chars | `422 Unprocessable Content` |

## Acceptance criteria

- **API-AUTH-001**: Given `POST /api/v1/auth/register` or `POST /api/v1/auth/account/password`, when the password (`password` or `new_password`) is shorter than 8 characters or lacks a number, a lowercase letter, or an uppercase letter, then the gateway rejects the request with `422 Unprocessable Content`; and given `POST /api/v1/auth/login`, when `email` is invalid or `password` is shorter than 8 characters, the gateway rejects the request with `422`.
- **WEB-AUTH-001**: Given `/auth/register`, `/settings` (Change password modal), and `/auth/login`, when inspected or validated with Zod schemas (`registerSchema`, `passwordChangeSchema`, `loginSchema`), then `/auth/register` and `/settings` render the Nuxt UI password strength indicator (`UInput` with `#trailing` visibility toggle, `UProgress` with `:max="4"`, `#password-strength` status text, and the 4-requirement checklist with `i-lucide-circle-check` / `i-lucide-circle-x`) and validate all 4 password rules via Zod (`strongPasswordSchema`) and `passwordChangeReady`, while `/auth/login` validates `z.email('Invalid email')` and `z.string('Password is required').min(8, 'Must be at least 8 characters')` on `<UAuthForm :schema="loginSchema">`.

## Security & privacy considerations

- Enforces minimum credential complexity on account creation and password rotation and validates login payloads uniformly via Zod on the client and Pydantic on the server. Passwords continue to never be logged or echoed in errors.

## Evaluation impact

- None.

## Open questions

- None.

## Verification

### 2026-11-17 · commit 2a0b84f (+ uncommitted changes)

- Criteria: API-AUTH-001, WEB-AUTH-001
- Red: 5 failing test(s) before implementation (`apps/api/tests/test_account_settings.py::test_invalid_bodies_are_rejected[POST-/password-body2]`, `apps/api/tests/test_account_settings.py::test_invalid_bodies_are_rejected[POST-/password-body3]`, `apps/api/tests/test_account_settings.py::test_invalid_bodies_are_rejected[POST-/password-body4]`)
- Green: 12 passing test(s)
- Gate: `mise run check` passed
