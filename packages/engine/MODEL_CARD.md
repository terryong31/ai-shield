# Model card: `baseline` classifier (the game's ML filter TF-IDF default)

> **Status.** Spec 0038 changed the ML filter: it runs only models that a player trains. The gateway
> still loads the bundled baseline at startup, but no check uses it. The `Quick screen` check was
> merged into the ML filter (spec 0035).

| | |
| --- | --- |
| **Artifact** | `src/shield_engine/models/baseline/` (`model.joblib`, `vectorizer.joblib`, `metadata.json`) |
| **Algorithm** | TF-IDF (max 5,000 features) → `SGDClassifier(loss="log_loss")` |
| **Output** | P(malicious) ∈ [0, 1]; the `ML filter` (`ml_classifier`) node maps it to `safe`, `suspicious`, or block with the player's `safe_threshold` and `block_threshold` |
| **Training data** | `data/seed/train.jsonl`: 20 hand-written prompts (10 malicious, 10 benign), repeated 20× |
| **Reproduce** | `mise run train`; digests are recorded in `metadata.json` and verified at load time |
| **Status** | A deliberately small game check. **Not a production control.** |

## Intended use

- The bundled model behind the game's **ML filter** node when `algorithm="tfidf"` is used without custom CSV training data: a fast, offline check players tune with two thresholds and combine with other checks.
- Its weaknesses are part of the game: players learn why one classifier is not
  enough and route `suspicious` prompts to further checks.

## Out of scope

- Screening real traffic, standalone moderation or compliance controls.
- Languages other than English.

## Historical evaluation

Before spec 0026 removed the evaluation harness, the classifier was measured on
a 40-prompt held-out set (20 malicious across 9 attack categories, 20 benign),
engine 0.1.0, 2026-09-23:

| Metric | Value |
| --- | --- |
| Precision | 1.000 |
| Recall | 0.550 |
| F1 | 0.710 |
| False-positive rate | 0.000 |
| Abstention (UNCERTAIN) | 0.375 |
| Latency p50 | ~0.13 ms |

40 examples is far too few for confident claims (the 95% confidence interval on
recall spans roughly 0.34–0.74). Notable misses: role-play jailbreaks ("You are
now DAN…") scored 0.04; gentle social engineering and spaced-out obfuscation
landed in UNCERTAIN.

## Risks and limitations

- A 20-example training set means the model mostly memorises surface
  vocabulary ("drop", "ignore", "export"). Paraphrases, other languages and
  encodings get through, which is why the game also offers Text cleaner, Word
  filter and the agent checks.
- The sensitive-keyword floor is substring-based (`"org"` matches
  "organisation"), which raises false escalations.
- The artifacts are pickles. They are hash-verified against `metadata.json`,
  but only load artifacts you built yourself.

## Changing it

Retrain with [Retrain the classifier](../../docs/how-to/retrain-the-classifier.md)
and record before/after game scores in a spec.
