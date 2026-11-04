# Tutorial 3: Your first spec-driven change

In this tutorial you will make a small change to the engine the way this
project makes every change: spec first, then a failing test, then the code.
You will teach the Layer 1 classifier that prompts mentioning "password" are
sensitive, so they are reviewed by Layer 2 instead of passing straight through.

You need the repository set up as in [Tutorial 1](01-run-the-demo.md), steps 1
to 3. Work on a branch so you can throw the change away afterwards:

```bash
git switch -c tutorial/password-keyword
```

## 1. See the problem

Ask the bundled classifier about a password prompt:

```bash
uv run python -c "
from shield_engine.models import load_baseline
print(load_baseline().score('How do I reset the admin password?'))"
```

You should see a `SAFE` verdict with a score of about 0.11 and
`sensitive_floor_applied: False`. With default settings, a `SAFE` prompt from
a caller without clearance never reaches Layer 2, and gets `ALLOW_ALL` tools.

The classifier already has a safety net for this: a list of sensitive keywords
(`salary`, `database`, `confidential`, …). A low score on a prompt that mentions
one is raised to 0.40, which is `UNCERTAIN`, so Layer 2 reviews it. "password"
is not on the list. That is the change you will make.

## 2. Scaffold a spec

```bash
mise run spec:new sensitive-keyword-password
```

The output is:

```
created specs/0009-sensitive-keyword-password/ (spec.md, plan.md, tasks.md)
next: fill in spec.md, add it to specs/README.md, open a PR for review
```

The number is the next free one. If other specs have been added since this
tutorial was written, yours will be higher; use your number wherever you see
`0009` below.

For a change this small you only need `spec.md`. Delete the other two:

```bash
rm specs/0009-sensitive-keyword-password/plan.md specs/0009-sensitive-keyword-password/tasks.md
```

## 3. Write the spec

Open `specs/0009-sensitive-keyword-password/spec.md`. Fill in the header and
the sections. Keep it short:

```markdown
# 0009 — Sensitive keyword password

- **Status:** Draft
- **Area:** ENG
- **Owner:** <your name>
- **Created:** <today>
- **Related:** spec 0002

## Problem

"How do I reset the admin password?" scores 0.11 (SAFE) on the baseline, so it
bypasses Layer 2 and receives ALLOW_ALL tools. Credential requests should be
reviewed.

## Goals

- Prompts that mention "password" are routed to Layer 2 when Layer 1 scores them low.

## Non-goals

- Retraining the model.

## Behaviour

"password" is added to `SENSITIVE_KEYWORDS`. The existing floor rule
(score < 0.35 on a sensitive topic becomes 0.40) then applies to it.

## Acceptance criteria

- **ENG-CLS-008**: Given text containing "password" and a model probability below 0.35, when scored, then the score is raised to 0.40, the verdict is UNCERTAIN and `sensitive_floor_applied` is true.

## Security & privacy considerations

More benign prompts reach Layer 2 (cost, latency). The floor can only raise
scores, so no prompt becomes less likely to be blocked.

## Evaluation impact

Abstention on `mise run eval` may rise slightly. Record before/after numbers.

## Open questions

None.
```

The criterion has an ID, `ENG-CLS-008`: area `ENG` (the engine), component
`CLS` (the classifier), and the next unused number. Check that nobody has used
it yet:

```bash
grep -rn "ENG-CLS-008" specs packages apps
```

No output means it is free.

Add a row for your spec to the index table in [`specs/README.md`](../../specs/README.md).

## 4. Accept the spec

In a real change you would now open a pull request with only the spec and ask
for review. For this tutorial, accept it yourself: change the status line to

```markdown
- **Status:** Accepted
```

Once a spec is `Accepted`, every criterion in it must have a test. Check:

```bash
mise run spec:check
```

It fails and names your criterion:

```
Acceptance criteria without a test:
  - ENG-CLS-008  (specs/0009-sensitive-keyword-password/spec.md)
```

This is the traceability rule doing its job. CI runs the same check.

## 5. Write a failing test

Open `packages/engine/tests/test_classifier.py`. It already has a helper,
`detector(probability)`, that builds a `ClassifierDetector` around a fake
model returning a fixed probability. Add this test at the end of the file:

```python
@pytest.mark.spec("ENG-CLS-008")
def test_password_is_a_sensitive_keyword() -> None:
    signal = detector(0.05).score("How do I reset the admin password?")

    assert signal.score == pytest.approx(0.40)
    assert signal.verdict is Verdict.UNCERTAIN
    assert signal.details["sensitive_floor_applied"] is True
```

`@pytest.mark.spec("ENG-CLS-008")` links the test to the criterion. That string
is what `spec:check` looks for.

Run just this test:

```bash
uv run pytest packages/engine/tests/test_classifier.py -k password
```

It fails:

```
>       assert signal.score == pytest.approx(0.40)
E       assert 0.05 == 0.4 ± 4.0e-07
...
FAILED packages/engine/tests/test_classifier.py::test_password_is_a_sensitive_keyword - assert 0.05 == 0.4 ± 4.0e-07
```

Good. The test fails for the reason you expect: the floor did not apply. A test
you have never seen fail proves nothing.

Run the traceability check again:

```bash
mise run spec:check
```

It now passes, because the ID appears in a test. Traceability and correctness
are separate checks: `spec:check` says a test exists, `pytest` says it passes.

## 6. Make it pass

Open `packages/engine/src/shield_engine/detectors/classifier.py` and add
`"password"` to the end of `SENSITIVE_KEYWORDS`:

```python
SENSITIVE_KEYWORDS: tuple[str, ...] = (
    "sales", "revenue", "employee", "salary", "database", "sql", "delete",
    "personal", "customer", "member", "boss", "org", "chart", "hierarchy",
    "email", "private", "confidential", "internal", "table", "drop", "password",
)  # fmt: skip
```

Run the test again:

```bash
uv run pytest packages/engine/tests/test_classifier.py -k password
```

It passes (`1 passed`). Now run the whole engine suite to check nothing else broke:

```bash
mise run test:engine
```

## 7. Measure the effect

This change affects detection, so the spec asks for before/after numbers. Run
the evaluation:

```bash
mise run eval
```

Compare the printed line with the baseline in the
[model card](../../packages/engine/MODEL_CARD.md#evaluation). You should see
precision, recall, F1 and false-positive rate unchanged, and `abstain` rise from
0.375 to 0.400:

```
n=40  precision=1.000  recall=0.550  f1=0.710  fpr=0.000  abstain=0.400  p50=0.13ms
```

(Latency varies by machine.) One benign prompt in the evaluation set, "How do I
reset my own password on the HR portal?", is now sent to Layer 2. That is the
cost the spec predicted. Paste the before and after lines into the spec's
"Evaluation impact" section.

## 8. Run the full gate

```bash
mise run check
```

This runs lint, type checks, all tests, `spec:check` and `contract:check`,
exactly as CI does. When it is green, set the spec's status to `Implemented`,
update the keyword list in the [engine reference](../reference/engine-api.md#classifierdetector),
and the change is ready for a pull request.

## 9. Throw it away

This was practice. Discard your edits and the new spec folder, then the branch:

```bash
git restore packages/engine specs/README.md
rm -r specs/0009-sensitive-keyword-password
git switch main
git branch -D tutorial/password-keyword
```

`git status` should now show a clean tree.

## What you have done

You went through the full loop: problem, spec with an ID, acceptance, a test
linked to the ID, red, green, measurement and the gate. Every change in this
repository follows these steps, whether a person or an AI agent does the work.

## Next steps

- [Write a spec](../how-to/write-a-spec.md) is the checklist version of steps 2 to 4.
- [Development process](../explanation/development-process.md) explains why the project works this way.
- [Work with AI agents](../how-to/work-with-ai-agents.md) shows how the same loop runs with Claude Code.
