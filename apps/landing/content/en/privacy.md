---
title: Privacy Policy
description: What ai-shield collects, why, where it is kept, for how long, its sub-processors, and your rights under Malaysia PDPA and GDPR.
version: '2.0'
effective: 2026-11-28
summary:
  - title: We collect little
    description: Your email, display name, boards, scores and purchases. We do not store the prompts you run or your own API keys.
    icon: i-lucide-database
    to: '#data-we-collect'
  - title: No tracking cookies
    description: We use only the cookies the game needs to sign you in. Site measurement is cookieless.
    icon: i-lucide-cookie
    to: '#cookies-and-browser-storage'
  - title: Named providers only
    description: Supabase, Vercel, Upstash, Stripe, Resend, Google, Groq and TypeSafe process data for us. Some are outside Malaysia.
    icon: i-lucide-server
    to: '#sub-processors'
  - title: You stay in control
    description: Export your data as JSON, change your details, or delete your account at any time from Settings.
    icon: i-lucide-user-cog
    to: '#your-rights'
---

## Who we are

::callout{icon="i-lucide-info"}
**In short:** one person runs ai-shield in Malaysia. Write to support@ai-shield.my with any privacy question.
::

Terry Ong (operating ai-shield in Malaysia) controls the personal data described here. This policy covers ai-shield.my, play.ai-shield.my, admin.ai-shield.my, and api.ai-shield.my. For privacy or PDPA inquiries, contact [support@ai-shield.my](mailto:support@ai-shield.my).

## Data we collect

::callout{icon="i-lucide-info"}
**In short:** we keep what the game needs to sign you in, save your progress and sell the pass. Prompts and your own API keys are never stored.
::

| Category | Data | Why | How long |
| --- | --- | --- | --- |
| Account | Email (lowercase), display name, plan (free or paid), pass end date, account creation date | Sign-in, daily limits for your plan, and your place on the leaderboard | Until you delete your account |
| Progress | Saved boards, best scores and medals, custom CSV rows uploaded to train the ML filter | Keep progress across devices, rank the leaderboard, run your ML filter | Boards and scores until reset or account deletion; trained ML models stay in memory for 30 minutes idle TTL |
| Anonymous play | Best scores of a non-signed-in session keyed by a hash of its session token | Move your scores to your account when you sign in | 7 days, or until you sign in |
| Prompts and BYOK keys | Wave prompts and Custom Sandbox API keys you type in the browser | Run checks and agent replies for that single run | Not stored. BYOK API keys stay in browser memory only |
| Payments | Pass purchases: id, amount, currency (USD), status, payment id, start and end dates | Grant 30-day passes and handle refunds or disputes. Card details stay with Stripe | Kept for accounting; your email is set to NULL when you delete your account |
| Security | SHA-256 hashed IPs in rate-limit counters, hashed session tokens, daily run counts, security audit logs | Prevent brute force, bots, and abuse | Rate-limit counters: 1 minute to 1 hour. Deleted account daily run counts: pruned after 30 UTC days |
| Site measurement | Cookieless aggregate page views and Core Web Vitals on ai-shield.my and play.ai-shield.my (auth query strings scrubbed) | Check availability and page speed | As set by Vercel |

## Cookies and browser storage

::callout{icon="i-lucide-info"}
**In short:** every cookie here is needed for the game to work. There are no advertising or tracking cookies.
::

| Name | Storage | Why | How long |
| --- | --- | --- | --- |
| `shield_player_session` | HttpOnly cookie (SameSite=Lax, Secure, play.ai-shield.my) | Player session (signed in or anonymous); the server stores a SHA-256 hash only | 8 hours or until sign-out |
| `shield_auth_browser` | HttpOnly cookie (SameSite=Lax, play.ai-shield.my) | Binds email confirmation and recovery links to the browser that asked for them | 30 to 60 minutes |
| `shield_session_hint` | Cookie (play.ai-shield.my) | Prevents a menu flash while the page loads; holds no email or token | Synced with the session |
| `shield_session` | HttpOnly cookie (SameSite=Strict, Secure, admin.ai-shield.my) | Isolated admin console access for operators only | 8 hours |
| `shield_anon_draft:v1:<level>` | localStorage (play.ai-shield.my) | Unsaved board draft before sign-in; holds no score | Until Restart, sign-in, or site data cleared |
| `ai-shield:tour-seen:<level>` | localStorage (play.ai-shield.my) | Remembers the level tours you have seen | Until site data cleared |
| Saved board and leaderboard cache | sessionStorage (play.ai-shield.my) | Faster tab loading | Until the tab closes |

## Sub-processors

::callout{icon="i-lucide-info"}
**In short:** these companies run parts of ai-shield for us. Each one gets only the data its job needs.
::

| Provider | Role | Why | How long |
| --- | --- | --- | --- |
| Supabase | Database and Auth | Stores accounts, progress, and purchases; verifies passwords | As above |
| Vercel | Hosting, BotID, Web Analytics, Speed Insights | Serves ai-shield.my, play.ai-shield.my, admin.ai-shield.my, and api.ai-shield.my | As set by Vercel |
| Redis (Upstash) | Short-lived counters and caches | Rate limits, auth-flow state, leaderboard cache, ephemeral ML models | Minutes to 2 days |
| Stripe | Hosted Checkout | Processes $5 USD 30-day Pass payments and refunds | As set by Stripe |
| Resend | Transactional and support email (SMTP) | Sends auth emails (no-reply@ai-shield.my) and support replies (support@ai-shield.my) | As set by Resend |
| Google (Gemini) and Groq | Campaign AI models | Run protected agents and checks on Medium and Hard levels | Per run, as set by the provider |
| TypeSafe | Jev node | Answers the yes-or-no questions of the Jev node when you use it | Per run, as set by the provider |
| OpenAI, Anthropic, OpenRouter | Optional BYOK providers | Called only when you supply your own API key in the Custom Sandbox | As set by your chosen provider |

## Cross-border transfers

::callout{icon="i-lucide-info"}
**In short:** some providers process data outside Malaysia, under contracts that keep it secure.
::

Your data may be processed outside Malaysia by our named sub-processors (Supabase, Vercel, Upstash Redis, Stripe, Resend, Google, Groq, TypeSafe, and BYOK providers OpenAI, Anthropic, and OpenRouter) under contractual security safeguards aligned with the PDPA Security Principle (Section 9) and Data Processing Addenda.

## Data breach notification

::callout{icon="i-lucide-info"}
**In short:** if a serious breach happens, we tell the regulator within 72 hours and tell you without delay.
::

If a personal data breach meets the statutory notification threshold under Malaysia's Personal Data Protection (Amendment) Act 2024, we notify the Personal Data Protection Commissioner (PDPC) within 72 hours and notify affected users without undue delay.

## Your rights

::callout{icon="i-lucide-info"}
**In short:** you can see, download, change or delete your data yourself, at any time.
::

You may access and export your account data as JSON at any time from [play.ai-shield.my/settings](https://play.ai-shield.my/settings) (Download my data), update your display name, email, or password, reset game progress, or delete your account permanently. Because we are an individual-operated service below the statutory DPO threshold, direct all privacy requests to [support@ai-shield.my](mailto:support@ai-shield.my).
