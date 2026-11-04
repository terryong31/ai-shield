# Security policy

AI S.H.I.E.L.D. is a security product, so a detection bypass counts as a vulnerability.

## Reporting

Please report **privately** through
[GitHub Security Advisories](https://github.com/terryong31/ai-shield/security/advisories/new).
Do not open public issues for:

- prompts that get past the pipeline and unlock tools they shouldn't (include the prompt, mode, clearance and the decision you observed);
- injection against the Layer 2 adjudicator itself;
- credential or data leakage, or authentication or authorisation flaws in the gateway;
- supply-chain issues, including model artifacts.

We aim to acknowledge reports within 3 working days and to agree a disclosure
timeline with you. We credit reporters unless you ask us not to.

## Scope and known limitations

The following are documented, not vulnerabilities. See
[docs/explanation/threat-model.md](docs/explanation/threat-model.md).

- The demo passphrase is a stand-in for real RBAC.
- The bundled Layer 1 baseline has limited recall ([model card](packages/engine/MODEL_CARD.md)).
- With no LLM provider configured, Layer 2 falls back to a conservative policy rather than a real judgement.

## Supported versions

Only the latest `main` receives fixes during the alpha.
