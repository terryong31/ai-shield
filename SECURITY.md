# Security policy

ai-shield is a prompt-injection defence game. Attacks inside a level are part of the game. Report problems that affect players, their data, payments or the server.

## Reporting

Please report **privately** through
[GitHub Security Advisories](https://github.com/terryong31/ai-shield/security/advisories/new).
Do not open public issues for:

- prompts that make the server-side model act outside a level (include the level, board and prompt);
- score or quota tampering;
- payment problems: a pass without a payment, a fake webhook, or a payment without a pass;
- credential or data leakage, or authentication or authorisation flaws in the gateway;
- supply-chain issues, including model artifacts.

We aim to acknowledge reports within 3 working days and to agree a disclosure
timeline with you. We credit reporters unless you ask us not to.

## Scope and known limitations

The following are documented, not vulnerabilities. See
[docs/explanation/threat-model.md](docs/explanation/threat-model.md).

- Admin accounts have no second factor; access is a password plus `app_metadata.role = "admin"`.
- The bundled baseline classifier has limited recall ([model card](packages/engine/MODEL_CARD.md)). No check uses it.
- With no LLM provider configured, agent levels run an offline stand-in.
- Production uses the Stripe sandbox, so a public test card gives the Paid tier.

## Supported versions

Only the latest `main` receives fixes during the alpha.
