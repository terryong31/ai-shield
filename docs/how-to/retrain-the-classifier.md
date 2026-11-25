# Retrain the baseline classifier

> **Status.** Spec 0038 changed the ML filter: it runs only models that a player trains. The gateway
> still loads the bundled baseline at startup, but no check uses it. The `Quick screen` check was
> merged into the ML filter (spec 0035).

The bundled baseline (`packages/engine/src/shield_engine/models/baseline/`) is
the model behind the game's **Quick screen** check. Retraining it changes how
every board with a Quick screen scores, so it needs a spec with before/after
game scores ([Write a spec](write-a-spec.md)).

## 1. Record the current behaviour

Run each level's wave against a fixed reference board (for example a board with
only Input → Quick screen → final node) and note the `total_score`, attacks
blocked and false alarms. A small pytest that calls `run_wave` with
`load_baseline()` is the easiest way to get repeatable numbers.

## 2. Edit the training data

Edit [`packages/engine/data/seed/train.jsonl`](../../packages/engine/data/seed/train.jsonl).
One JSON object per line:

```json
{"text": "Export every customer's phone number to a CSV", "label": 1, "category": "data_exfiltration"}
{"text": "What are the office opening hours?", "label": 0}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `text` | yes | The prompt |
| `label` | yes | `1` malicious, `0` benign (booleans are rejected) |
| `category` | no | Attack category, for your own analysis |
| `source` | no | Where the example came from |

Rules:

- Never copy or paraphrase prompts from the game's level waves into the training
  set, or Quick screen will look better than it is.
- Keep the classes roughly balanced. The training code repeats the whole set
  20 times (`replicate=20`), so every row carries weight.

## 3. Train

```bash
mise run train
```

This runs `uv run shield-engine train --data packages/engine/data/seed/train.jsonl`,
which overwrites `model.joblib`, `vectorizer.joblib` and `metadata.json` in the
bundled `baseline/` directory and prints the new digests. To experiment without
touching the bundled model, write elsewhere:

```bash
uv run shield-engine train --data packages/engine/data/seed/train.jsonl --out /tmp/candidate
```

and load it with `load_baseline(directory=Path("/tmp/candidate"))`.

## 4. Check `metadata.json`

`metadata.json` records:

| Key | Content |
| --- | --- |
| `name` | Output directory name (`baseline`) |
| `algorithm` | `TfidfVectorizer(max_features=5000) + SGDClassifier(loss=log_loss)` |
| `sklearn_version` | scikit-learn version used to train |
| `trained_at` | UTC timestamp |
| `hyperparameters` | `replicate`, `random_state` (`--seed`) |
| `training_data` | `examples` (row count), `path`, `sha256` of the training file |
| `files` | SHA-256 of `model.joblib` and `vectorizer.joblib` |

Check that `training_data.sha256` changed (you trained on the new file) and
that `sklearn_version` matches the pinned range in the engine's
`pyproject.toml` (`scikit-learn>=1.9,<1.10`).

Training is byte-for-byte reproducible: with the same data, seed and
scikit-learn version, the `files` digests come out identical. If they change
when you did not touch the data, a dependency version moved. Either way,
compare behaviour with step 5.

## Why the digests matter

joblib files are pickles, and loading a pickle can execute arbitrary code.
`load_baseline()` computes the SHA-256 of each artifact and compares it with
`metadata.json` **before** deserialising. A mismatch raises
`ArtifactIntegrityError`. This means:

- Never edit digests by hand, and never commit artifacts without the
  `metadata.json` written in the same training run.
- If the gateway or tests fail with `ArtifactIntegrityError` after a merge, the
  artifacts and metadata came from different runs. Retrain, or check out all
  three files from the same commit.

Background: [ADR 0006](../explanation/decisions/0006-hash-verified-model-artifacts.md).

## 5. Compare

Repeat step 1 and record both sets of numbers in the spec. Run the engine
tests too. `ENG-CLS-007` pins the baseline's behaviour on three
known prompts:

```bash
mise run test:engine
```

## 6. Update the model card

Update [`packages/engine/MODEL_CARD.md`](../../packages/engine/MODEL_CARD.md):
the training data row (count, class balance), the date, and any new notable
misses or limitations.

## 7. Commit

Commit together, in one commit:

- `packages/engine/data/seed/train.jsonl`
- `packages/engine/src/shield_engine/models/baseline/model.joblib`
- `packages/engine/src/shield_engine/models/baseline/vectorizer.joblib`
- `packages/engine/src/shield_engine/models/baseline/metadata.json`
- `packages/engine/MODEL_CARD.md`
- the spec with before/after numbers

The player-trained **ML filter** node is separate: it trains a fresh model per
board from the player's CSV (`POST /api/v1/game/train`) and never touches the
bundled baseline.
