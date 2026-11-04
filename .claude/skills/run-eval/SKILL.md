---
name: run-eval
description: Benchmark the prompt-injection engine and compare against the recorded baseline. Use when a change may affect detection quality, or when asked for metrics.
---

# Run an evaluation

1. Baseline first. On the unchanged code (e.g. `git stash`, or `main`), run
   `mise run eval`, then copy `reports/eval-classifier.json` to `reports/before.json`.
2. Apply the change and run `mise run eval` again.
3. For the LLM layers (costs money, needs `GROQ_API_KEY`):
   `uv run shield-engine eval --data packages/engine/data/seed/eval.jsonl --pipeline full --report reports/eval-full.json`.
   Ask the human before running this.
4. Compare precision, recall, F1, false-positive rate, abstention rate and p50/p95
   latency. Present a before/after table. Remember that the seed eval set has
   only 40 rows, so treat differences of a single example as noise.
5. Check that the dataset SHA-256 matches between runs; otherwise the comparison is invalid.
6. If the bundled baseline changed, update the Evaluation table in
   `packages/engine/MODEL_CARD.md`. Record the numbers in the relevant spec under
   "Evaluation impact".
7. Never tune on `eval.jsonl`. New training examples go in `train.jsonl`, and new
   evaluation examples must be written independently.
