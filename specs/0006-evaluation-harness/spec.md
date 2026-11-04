# 0006 — Evaluation harness

- **Status:** Implemented
- **Area:** ENG
- **Created:** 2026-09-23
- **Related:** [evaluation methodology](../../docs/explanation/evaluation-methodology.md)

## Problem

There was no way to measure detection quality. Research claims and
regressions need a reproducible benchmark with standard metrics.

## Goals

- Load labelled JSONL datasets.
- Run any screener (classifier only, or full pipeline) over a dataset.
- Report standard binary-classification metrics plus latency and abstention.
- Emit a machine-readable JSON report for tracking over time.

## Behaviour

Dataset rows: `{"text": str, "label": 0|1, "source"?: str, "category"?: str}`
where `1` means malicious.

A prediction is **positive** when the decision is blocked. UNCERTAIN verdicts
that were not blocked count as negatives but are also reported as the
*abstention rate*, so a pipeline cannot hide behind "uncertain".

CLI: `shield-engine eval --data <jsonl> [--report <json>] [--pipeline classifier|full]`.

## Acceptance criteria

- **ENG-EVAL-001**: Given a JSONL file with a malformed row (bad JSON, missing field, or label not in {0,1}), when loaded, then `DatasetError` is raised naming the 1-based line number.
- **ENG-EVAL-002**: Given predictions and labels, then the confusion matrix, precision, recall, F1, false-positive rate and accuracy are computed correctly, and zero denominators yield 0.0 instead of raising.
- **ENG-EVAL-003**: When a dataset is evaluated, then blocked decisions count as positive, the abstention rate is the share of UNCERTAIN verdicts, and p50/p95 latency in milliseconds is reported.
- **ENG-EVAL-004**: When the CLI runs with `--report`, then a JSON report containing the metrics, dataset path, dataset SHA-256 and engine version is written.

## Evaluation impact

This spec *is* the evaluation. Baseline numbers live in the model card.

## Open questions

None.

## Verification

### 2026-09-23 · commit 489ecc5 (+ uncommitted changes) · backfilled

- Criteria: ENG-EVAL-001, ENG-EVAL-002, ENG-EVAL-003, ENG-EVAL-004
- Red: observed during the monorepo refactor, before `sdd` existed; not machine-recorded
- Green: 9 passing test(s)
- Gate: `mise run check` passed
