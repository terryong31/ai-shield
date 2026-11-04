# Model card: `baseline` Layer 1 classifier

| | |
| --- | --- |
| **Artifact** | `src/shield_engine/models/baseline/` (`model.joblib`, `vectorizer.joblib`, `metadata.json`) |
| **Algorithm** | TF-IDF (max 5,000 features) → `SGDClassifier(loss="log_loss")` |
| **Output** | P(malicious) ∈ [0, 1], mapped to SAFE ≤ 0.15 < UNCERTAIN < 0.85 ≤ MALICIOUS |
| **Training data** | `data/seed/train.jsonl`: 20 hand-written prompts (10 malicious, 10 benign), repeated 20× |
| **Reproduce** | `mise run train`; digests are recorded in `metadata.json` and verified at load time |
| **Status** | Research baseline. **Not suitable as a sole production control.** |

## Intended use

- The fast, offline first layer of the AI S.H.I.E.L.D. pipeline. Its job is to
  catch blatant attacks cheaply and to route everything ambiguous to Layer 2.
- A fixed reference point for measuring improvements with `mise run eval`.

## Out of scope

- Standalone moderation or a compliance control.
- Languages other than English.
- Domains other than the demo's enterprise-assistant setting (HR, sales, catalogue).

## Evaluation

Held-out set `data/seed/eval.jsonl`: 40 prompts (20 malicious across 9 attack
categories, 20 benign), written independently of the training set.
Classifier-only pipeline (`--pipeline classifier`), engine 0.1.0, 2026-09-23:

| Metric | Value |
| --- | --- |
| Precision | 1.000 |
| Recall | 0.550 |
| F1 | 0.710 |
| False-positive rate | 0.000 |
| Abstention (UNCERTAIN → Layer 2) | 0.375 |
| Latency p50 | ~0.13 ms |

Read these numbers with care:

- **40 examples is far too few for confident claims.** The 95% confidence
  interval on recall spans roughly 0.34–0.74.
- **Abstention is high by design.** Without Layer 2, uncertain prompts are
  *allowed with a `RESTRICTED` policy*, so recall here understates the full
  pipeline and overstates what the classifier alone can do.
- **Notable misses:** role-play jailbreaks ("You are now DAN…") scored 0.04
  (SAFE). Gentle social-engineering ("just this once, it's an emergency") and
  spaced-out obfuscation landed in UNCERTAIN.
- **Benign prompts routed to Layer 2** include anything mentioning sensitive
  nouns (the sensitive-keyword floor) and short phrases outside the training
  vocabulary ("Thanks, that answered my question!").

## Risks and limitations

- A 20-example training set means the model mostly memorises surface
  vocabulary ("drop", "ignore", "export"). Paraphrases, other languages,
  encodings and indirect injection via documents will get through.
- The sensitive-keyword floor is substring-based (`"org"` matches
  "organisation"), which raises false escalations.
- Online learning (`learn()`) updates weights from single reviewer labels,
  so it can be poisoned by a malicious reviewer. Review access must be trusted.
- The artifacts are pickles. They are hash-verified against `metadata.json`,
  but only load artifacts you built yourself.

## Improving it

Track every change with a spec and before/after numbers from `mise run eval`.
Promising directions: public injection corpora (e.g. deepset
`prompt-injections`, Lakera Gandalf), a small fine-tuned encoder, character
n-grams for obfuscation, and a larger, category-balanced evaluation set.
