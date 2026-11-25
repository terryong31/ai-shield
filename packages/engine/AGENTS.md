# AGENTS.md: packages/engine

The game's check library. Root rules in [../../AGENTS.md](../../AGENTS.md) apply; these add to them.

## Map

| Module | Responsibility | Spec |
| --- | --- | --- |
| `game/` | Board interpreter, check nodes, levels, AI Agent, custom sandbox, scoring | 0016, 0020–0022 |
| `detectors/classifier.py` | Baseline TF-IDF + SGD classifier with a sensitive-topic floor (no check uses it since spec 0038) | 0002 |
| `untrusted.py` | `wrap_untrusted()`: prompts reach an LLM only as inert, delimited data | 0026 |
| `models/` | Bundled, hash-verified baseline artifacts | 0002 |
| `training.py`, `dataset.py`, `cli.py` | Retrain the baseline (`mise run train`) | 0002 |
| `adapters/groq.py` | Groq chat model (optional `groq` extra) | none |
| `ports.py` | The only interfaces to the outside world | none |
| `testing.py` | Public test doubles; use these, don't hand-roll mocks | none |

## Rules

- Allowed runtime deps: stdlib, `scikit-learn`, `joblib`. Anything else must be
  an optional extra imported only inside `adapters/`.
- No I/O at import time, no env vars, no global singletons. Configuration is
  passed in via constructors and function arguments.
- Public types are frozen dataclasses or `StrEnum`s. Adding a field is fine;
  renaming or removing one is a breaking change that needs a spec.
- Changes to scoring or to the bundled classifier must record before/after game
  scores (or classifier behaviour) in their spec. If the baseline changes,
  update `MODEL_CARD.md`.
- Artifacts: retrain only via `mise run train`, which rewrites `metadata.json`
  digests. Never hand-edit digests.

## Commands

```bash
mise run test:engine        # with 90% coverage floor
uv run pytest packages/engine -k game
mise run train
```
