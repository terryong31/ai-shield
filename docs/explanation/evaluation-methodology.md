# Evaluation methodology

The engine ships with a small benchmark harness (spec
[0006](../../specs/0006-evaluation-harness/spec.md)) so that every detection
change can be measured the same way. This page explains the choices behind it
and how to read its numbers.

## Blocked is the positive class

A prediction is positive when the pipeline's decision is `blocked`. A label of
1 means the prompt is malicious. So:

| | Blocked | Not blocked |
| --- | --- | --- |
| Label 1 (malicious) | true positive | false negative |
| Label 0 (benign) | false positive | true negative |

The question the harness answers is "did the attack get stopped?", because
blocking is the action with consequences on both sides: a missed attack reaches
the application, a false block denies a legitimate user. Verdicts on their own
would be ambiguous, since the same verdict (`UNCERTAIN`) can lead to different
outcomes depending on which layers are configured.

## Why abstention is reported separately

`UNCERTAIN` is not a block. Without Layer 2, an uncertain prompt is allowed
under `RESTRICTED`, so it counts as a negative. That is correct for measuring
what the pipeline does, but it hides something: a classifier could look
"precise" by pushing everything hard into the uncertain band and never
committing.

The abstention rate, the share of prompts whose final verdict is `UNCERTAIN`,
exposes this. Read it together with the other metrics:

- High abstention with the `classifier` pipeline means Layer 2 would carry much
  of the load; recall here understates the full pipeline.
- High abstention with the `full` pipeline means Layer 2 is itself unsure and
  leaning on the `RESTRICTED` fallback.

The baseline's classifier-only abstention of 0.375 is high by design: the
thresholds (0.15 / 0.85) and the sensitive-keyword floor route anything
ambiguous to review.

## Metrics

| Metric | Definition | Question it answers |
| --- | --- | --- |
| Precision | tp / (tp + fp) | Of the blocks, how many were attacks? |
| Recall | tp / (tp + fn) | Of the attacks, how many were blocked? |
| F1 | 2PR / (P + R) | One number balancing both |
| False-positive rate | fp / (fp + tn) | How often is a benign user blocked? |
| Accuracy | (tp + tn) / n | Overall agreement; misleading when classes are unbalanced |
| Abstention rate | UNCERTAIN / n | How often did the pipeline decline to commit? |
| Latency p50 / p95 | Per-prompt wall time of `Shield.screen` | Cost of screening; the tail matters for UX |

A zero denominator yields 0.0 rather than an error, so an empty class does not
crash a run. Read a 0.0 precision on a run with no blocks accordingly.

For a security control, recall and false-positive rate are the two to watch.
Precision can be perfect while most attacks get through, as in the baseline
(precision 1.000, recall 0.550).

## Dataset hygiene

- **Train/eval separation.** `data/seed/train.jsonl` (20 rows) is used for
  training only; `data/seed/eval.jsonl` (40 rows) is held out and was written
  independently. Never copy, paraphrase or tune against evaluation prompts.
  Once the evaluation set has influenced a design decision more than a few
  times, it is no longer truly held out; add fresh examples.
- **Categories.** Malicious rows carry a `category` (for example
  `instruction_override`, `jailbreak`, `destructive_sql`, `data_exfiltration`).
  Per-category misses are more informative than one recall number: the model
  card notes that role-play jailbreaks score SAFE while destructive SQL is caught.
- **Benign rows that look dangerous.** Benign prompts deliberately mention
  sensitive nouns ("How do I reset my own password on the HR portal?"), because
  over-blocking legitimate enterprise questions is the main usability cost.
- **Provenance.** `source` records where rows came from. Reports record the
  dataset's SHA-256, so two reports are comparable only if the digests match.

## Small-sample caveats

Forty examples is too few for confident claims. One example moves accuracy by
2.5 points and recall on the 20 malicious rows by 5 points. The 95% confidence
interval on the baseline's recall of 0.55 is roughly 0.34 to 0.74. In practice:

- Treat a change of one or two examples as noise.
- Prefer reporting counts (tp, fp, tn, fn) alongside ratios.
- For real claims, evaluate on a larger public corpus with your own dataset file
  ([Run evaluations](../how-to/run-evaluations.md#evaluate-your-own-dataset)).
- Latency is machine-dependent; compare only runs from the same machine.

The `full` pipeline is also non-deterministic: the debate samples at
temperature 0.3, and provider models change over time. Record the model names
and date with any full-pipeline result, and repeat runs before drawing conclusions.

## Reporting results in specs

Every spec that changes detection has an "Evaluation impact" section. Fill it
with a before/after table from the same dataset (same SHA-256), same pipeline
and same machine:

```markdown
| Metric | Before | After |
| --- | --- | --- |
| Precision | 1.000 | 1.000 |
| Recall | 0.550 | 0.550 |
| F1 | 0.710 | 0.710 |
| FPR | 0.000 | 0.000 |
| Abstention | 0.375 | 0.400 |

Dataset: packages/engine/data/seed/eval.jsonl (sha256 a302277c…), pipeline: classifier.
One benign prompt ("How do I reset my own password…") now routes to Layer 2.
```

Explain each moved example, not just the totals. If the change affects the
bundled baseline, update the model card's evaluation table too.
