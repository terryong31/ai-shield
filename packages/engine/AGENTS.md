# AGENTS.md: packages/engine

The deflector engine. Root rules in [../../AGENTS.md](../../AGENTS.md) apply; these add to them.

## Map

| Module | Responsibility | Spec |
| --- | --- | --- |
| `pipeline.py` | `Shield`: routes a prompt through the layers to a `Decision` | 0001 |
| `detectors/classifier.py` | Layer 1 TF-IDF + SGD, sensitive floor, feedback override | 0002 |
| `detectors/moderation.py` | Llama Guard parsing, fail-open/closed | 0003 |
| `adjudication/debate.py` | Layer 2 Analyst/Warden debate, untrusted-prompt wrapping | 0004 |
| `policy.py` | Deterministic policy → tools gate | 0005 |
| `evaluation/`, `cli.py` | Benchmark harness and `shield-engine` CLI | 0006 |
| `models/` | Bundled, hash-verified artifacts | 0002 |
| `ports.py` | The only interfaces to the outside world | none |
| `testing.py` | Public test doubles; use these, don't hand-roll mocks | none |

## Rules

- Allowed runtime deps: stdlib, `scikit-learn`, `joblib`. Anything else must be
  an optional extra imported only inside `adapters/`.
- No I/O at import time, no env vars, no global singletons. Configuration is
  passed in via constructors and `ShieldConfig`.
- Public types are frozen dataclasses or `StrEnum`s. Adding a field is fine;
  renaming or removing one is a breaking change that needs a spec.
- Anything that changes detection behaviour must come with before/after
  `mise run eval` numbers in its spec. If the change affects the baseline, update
  `MODEL_CARD.md`.
- Artifacts: retrain only via `mise run train`, which rewrites `metadata.json`
  digests. Never hand-edit digests.

## Commands

```bash
mise run test:engine        # with 90% coverage floor
uv run pytest packages/engine -k debate
mise run eval
```
