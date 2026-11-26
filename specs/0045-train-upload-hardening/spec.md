# 0045 — Training upload hardening and server-held models

- **Status:** Implemented
- **Area:** ENG | API | WEB
- **Owner:** Terry Ong
- **Created:** 2026-11-23
- **Related:** [0016-game-engine](../0016-game-engine/spec.md) (API-GAME-006), [0038-ml-classifier-user-data-only](../0038-ml-classifier-user-data-only/spec.md) (ENG-ML-002/003, API-ML-001/002), [0022-game-custom-sandbox](../0022-game-custom-sandbox/spec.md), [0023-game-saved-boards](../0023-game-saved-boards/spec.md), [0043](../0043-rate-limiting-and-client-ip/spec.md) (per-minute limit, BotID)

## Problem

`POST /game/train` (`routers/game.py` `train_game_classifier`) needs no session,
has no quota and no size limits, and trains scikit-learn on the event loop:

- `GameTrainRequest` takes `csv_text: str | None` and
  `dataset: list[dict[str, Any]] | None` with no length, row or character caps.
- `parse_dataset_csv` (engine `game/__init__.py`) treats any label it does not
  recognise as `0` (silent default), skips rows with fewer than two cells,
  accepts `is_attack` / `target` headers or no header, and keeps control
  characters.
- `_fit_custom_pipeline` does `int(r.get("label", 0))`, so a non-numeric label
  in `dataset` raises `ValueError` → `500`.
- `TfidfVectorizer(ngram_range=(1, 2))` has no `max_features`.
- Training runs synchronously inside the request, blocking the event loop.
- The response echoes every training row; the client stores them in the
  `ml_classifier` node's `config.dataset`, the engine **refits the model from
  those rows for every message of every `/game/run`**, and the rows are kept in
  saved boards and in recorded scores' `board_json`. Any client (including
  anonymous) can inject arbitrary training data straight into `/game/run`.

## Goals

- Only signed-in players train, under daily caps.
- Uploaded CSV text and rows are validated, fitted once, then discarded: never
  returned, saved, logged or written to disk.
- The fitted model is held server-side, signed, short-lived and purged when the
  player leaves; boards carry only an opaque `model_id`.
- `/game/run` never trains and never accepts training data.
- Bounded size, strict labels, clean text, bounded CPU, no `500`s.

## Non-goals

- Multipart upload or any server-side file storage (stays JSON `csv_text`).
- Durable models: models are temporary by design; a saved board needs a retrain.
- CSV export or download. If it is ever added, cells starting with `=`, `+`,
  `-` or `@` must be escaped (CSV/formula injection).
- The custom **wave** dataset (`CustomRunSchema.dataset`, max 50 rows of
  `normal`/`attack`) is unchanged by this spec.
- Changing the allowlisted algorithms or the classifier routing thresholds.
- New dependencies: stdlib `pickle`, `hmac`, `hashlib`, `secrets` (or the
  `joblib` that ships with scikit-learn) only.

## Behaviour

### Who can train, and how often

| Player | `POST /game/train` |
| --- | --- |
| No session / unknown token | `403` "Sign in to train the ML filter." |
| Anonymous session | `403` (same) |
| Signed-in free | 3 successful trainings per UTC day, then `429` |
| Signed-in paid | 200 successful trainings per UTC day, then `429` |

Only `422` (`BoardValidationError` / `ModelTooLargeError`), `413` and BotID or rate-limit
refusals do not count against the daily training limit. A `503` timeout **does**
count because CPU was spent, while the child worker process is killed immediately. Spec 0043 also applies (10 per minute per account, and Vercel
BotID in production). The tutorial level **easy-3** ("Train Your First Guard")
therefore needs sign-in; anonymous players see a sign-in prompt there.

`PlayerSessionStatus` gains `daily_train_limit: int | None` (`3` free, `200`
paid, `0` anonymous) and `train_runs_used: int`. The count lives in a new
`train_runs` column of `players.daily_usage` (migration via
`mise run db:migration`; SQLite no longer exists, spec 0046).

### Mode and input limits

`GameTrainRequest` gains `level_id: RunLevelId | None = None`. `level_id == "custom"` selects custom
limits and is allowed only for paid players (`403` "Custom mode is for paid
players."). Anything else is campaign mode.

| Limit | Campaign | Custom (paid) | Error |
| --- | --- | --- | --- |
| Request body | 128 KB (131,072 bytes) | 1.25 MB (1,310,720 bytes) | `413` |
| Training rows | 200 | 2000 | `422` |
| Minimum rows | 2, with both labels present | same | `422` |
| `text` length after cleaning | 1–500 characters | same | `422` |

The body is checked first against the custom cap (`Content-Length` and the
actual length) before parsing; after parsing, the campaign cap applies when
`level_id != "custom"`.

### Dataset rules (one engine validator)

Pure engine function `validate_training_rows(rows, *, max_rows)` returns
cleaned `(text, label)` rows or raises `BoardValidationError` naming the first
bad row (1-based data row number, header excluded). `parse_dataset_csv` and the
`/game/train` `dataset` path both use it.

- **Header:** the CSV's first row must be exactly `text,label` (trimmed,
  case-insensitive), else `422` "The first row must be the header text,label."
- **Shape:** every data row has exactly 2 cells, else `422` "Row N must have exactly 2 columns."
- **Labels:** `0`, `1`, `safe`, `attack` (trimmed, case-insensitive) → `0`,
  `1`, `0`, `1`. Anything else rejects the whole upload: `422` "Row N has label
  'x'; use 0, 1, safe or attack." In `dataset` JSON, `label` is `int | str`
  under the same rules.
- **Text cleaning:** remove NUL and other control characters (Unicode `Cc`,
  except `\t`, `\n`, `\r`, which become a space), NFC-normalise, trim. Empty →
  `422` "Row N has no text."; over 500 characters → `422` "Row N is longer than 500 characters."
- **Typed schema:** `GameTrainRequest.dataset` is `list[TrainingRowSchema] |
  None` (`text: str`, `label: int | str`, `extra="forbid"`). No input gives `500`.

### Fit once, sign, store, discard

1. Validate (above) and atomically reserve one daily train slot
   (`players.reserve_daily_usage` RPC / lock), then fit once with
   `TfidfVectorizer(ngram_range=(1, 2), max_features=5000)` via a persistent warm
   child worker (`TrainWorkerRunner`) that imports `scikit-learn` once on
   startup and emits `{"ready": true}` before the per-fit
   `TRAIN_TIMEOUT_SECONDS` (10 s) timer begins. A fit timeout kills the child
   process (`SIGKILL`) so a fresh worker spawns on the next request, keeps the
   consumed slot, and answers `503` "Training took too long. Try a smaller dataset.".
2. Serialise the fitted pipeline and sign it (below). A signed blob larger than
   `MODEL_MAX_BYTES` (1 MB, a constant; Upstash's per-request limit) releases
   the reserved train slot and answers `422`
   "The trained model is too large. Use fewer rows.".
3. Store it in the `TrainedModelStore` under a new random `model_id`
   (`secrets.token_urlsafe(16)`), owned by the session.
4. **One model per session** (user decision): storing the new model atomically
   replaces the session's earlier model, whichever ML filter node it was trained
   for, and deletes it. There is never more than one live model per session.
5. Discard the CSV text and rows. They are never returned, stored, logged or
   written to disk.

Response `GameTrainResponse`: `model_id`, `algorithm`, `sample_count`,
`accuracy`, `expires_at` (now + idle TTL). **No `dataset` field.**

### Signing (pickle safety)

New setting `MODEL_SIGNING_KEY: SecretStr | None`.

- `APP_ENV=production` and unset: `/game/train` answers `503` "Training is
  unavailable." and the gateway logs an error at startup; `/game/run` treats
  every `model_id` as untrained.
- `APP_ENV=development` and unset: a random per-process key is generated at
  startup (models do not survive a restart, which is fine locally).

Stored blob = `version byte ‖ HMAC-SHA256(key, owner_hash ‖ model_id ‖ payload) ‖ payload`.
Binding owner and `model_id` into the MAC means a blob copied to another key
fails verification. On load the MAC is verified with `hmac.compare_digest`
**before** unpickling. A wrong MAC, unknown version or truncated blob is never
unpickled: the entry is deleted, a warning is logged (no blob content), and the
node is treated as untrained. The client never receives a blob, only
`model_id`.

### `TrainedModelStore` (gateway)

| Backend | When | Storage |
| --- | --- | --- |
| Redis | `REDIS_URL` set (Upstash in production, container's existing client) | `mlmodel:<owner_hash>` → `model_id` + blob (one key per session, so a write replaces atomically), with TTL; set `mlmodels:acct:<sha256(email)>` indexes the account's owners |
| In-memory | otherwise (local dev) | dict with the same expiry semantics and a fake-able clock |

Never the local filesystem (Vercel serverless has no persistent disk).
`owner_hash` is the SHA-256 of the session token, so raw tokens are never
stored. A session holds at most one trained model.

### Purge rules

A model is deleted when any of these happens:

| Trigger | Mechanism |
| --- | --- |
| (a) Player leaves the game | Client sends `DELETE /game/models` on route leave, and `navigator.sendBeacon` on `pagehide` (beacon is a `POST /game/models/purge`, since `sendBeacon` cannot send `DELETE`). Both purge every model of the session; `204`, idempotent. |
| (b) 30 minutes idle | Sliding TTL `MODEL_IDLE_TTL_SECONDS = 1800` (constant), set on store and refreshed on each `/game/run` that loads the model (both `mlmodel:<owner_hash>` and `mlmodels:acct:<sha256(email)>`). |
| (c) Retrain, changed dataset, or training another ML filter | Any successful `/game/train` replaces the session's one model (above). |
| (d) Logout, session revoke, account delete | `POST /auth/logout`, the password-change "sign out other sessions", and `DELETE /account` purge the affected sessions' / account's models. |

### `/game/run`

- An `ml_classifier` node's config holds `model_id` (string), never `dataset`.
- Only the `ml_classifier` node whose `model_id` equals the session's current
  model is trained. Every other ML filter node on the board (an older or foreign
  `model_id`, or none) is untrained and listed in `untrained_model_nodes`.
  A board with `config.dataset` on any node answers `422` "Training data is not
  accepted here. Train the ML filter first." and nothing is counted.
- The gateway loads each `model_id` for the current session before the run,
  verifies and unpickles it, refreshes its TTL, and passes the loaded models to
  the engine. **No fitting happens on `/game/run`.**
- A missing, expired, foreign (other session) or unverifiable `model_id`
  behaves as untrained ("Model not trained", routes `safe`, as today), and
  `GameRunResponse` gains `untrained_model_nodes: list[str]` (node ids) so the
  UI can prompt a retrain.
- Anonymous sessions own no models, so their `ml_classifier` nodes are always
  untrained.

### Saves and scores

`PUT /game/saves/{level_id}` and score recording strip `model_id` and
`dataset` from every `ml_classifier` config before storing (`board_json`
included). `GET /game/saves/{level_id}` strips them too (older saves may still
hold `dataset`), so a loaded board's ML filter is untrained and needs a retrain.

### Engine (public API change, approved by the user)

The engine stays pure: no env vars, no I/O, no store.

- New: `fit_classifier(*, algorithm, rows) -> FittedClassifier` (frozen
  dataclass: `model`, `algorithm`, `sample_count`, `accuracy`).
- New: `sign_model(model, *, key: bytes, context: bytes) -> bytes` and
  `load_signed_model(blob, *, key: bytes, context: bytes) -> ProbabilityModel`
  (raises `ModelSignatureError` before any unpickling on a bad MAC).
- New port in `shield_engine/ports.py`: `ProbabilityModel` Protocol
  (`predict_proba(texts) -> ...`).
- Changed: `run_wave`, `run_single_message`, `run_custom_wave`,
  `run_custom_message` gain `ml_models: Mapping[str, ProbabilityModel] | None`
  keyed by `model_id`; the `ml_classifier` branch looks the node's `model_id`
  up there and **no longer reads or fits `config.dataset`**.
- Changed: `train_custom_classifier` / `TrainingSummary` lose the `dataset`
  echo (breaking: `TrainingSummary.dataset` removed); `/game/train` uses
  `fit_classifier`.
- New: `validate_training_rows`, `strip_training_data(board) -> BoardGraph`.

### Web client

- The training panel says in plain words: "Your file is not stored. Only the
  trained model is kept, temporarily, and it is deleted when you leave the
  game, after 30 minutes idle, or when you retrain."
- Train button, file input and CSV textarea are disabled for anonymous players,
  with a "Sign in to train" link to `/auth/login`.
- Before reading a file, the client rejects files larger than the mode's body
  cap (128 KB / 1.25 MB); `accept=".csv"` is a hint only.
- Files are decoded with `TextDecoder('utf-8', { fatal: true })`; invalid UTF-8
  shows "The file must be UTF-8 text." and nothing is sent.
- After training, the node stores `model_id` only (no rows), and retraining
  replaces the earlier model.
- When the player trains an ML filter while a different ML filter node already
  holds the session's model, the client warns first: "Training this filter
  replaces your earlier trained model. The other ML filter will need a retrain."
- When a run reports a node in `untrained_model_nodes`, or a saved board loads,
  the ML filter shows a "Retrain needed" state.
- On leaving `/game` and on `pagehide` the client purges the session's models.
- Remaining trainings (`daily_train_limit - train_runs_used`) are shown.

### Contract changes (`mise run contract`)

- `GameTrainRequest`: `level_id`, typed `dataset` rows.
- `GameTrainResponse`: `model_id`, `expires_at`; `dataset` removed.
- `GameRunResponse`: `untrained_model_nodes`.
- `PlayerSessionStatus`: `daily_train_limit`, `train_runs_used`.
- New `DELETE /game/models` and `POST /game/models/purge` (`204`).
- `/game/train`: documented `403`, `413`, `429`, `503`.

## Acceptance criteria

### Validation (engine)

- **ENG-TRAIN-001**: Given CSV text whose first row is not exactly `text,label` (missing, `text,is_attack`, `label,text`), when `parse_dataset_csv` runs, then it raises `BoardValidationError` naming the header; `Text, Label ` is accepted.
- **ENG-TRAIN-002**: Given a CSV whose 3rd data row has label `maybe`, then `BoardValidationError` names row 3 and the label, and no rows are returned (whole upload rejected).
- **ENG-TRAIN-003**: Given labels `0`, `1`, ` SAFE `, `Attack`, then they parse to `0`, `1`, `0`, `1`; given `true`, `yes`, `malicious`, `2` or empty, each is rejected.
- **ENG-TRAIN-004**: Given a data row with 1 or 3 cells, then `BoardValidationError` names that row.
- **ENG-TRAIN-005**: Given row text containing NUL, `\x07` and a tab, and a decomposed `é` (`e` + U+0301), then the cleaned text has no control characters, the tab became a space, and the `é` is U+00E9.
- **ENG-TRAIN-006**: Given a row whose text is only control characters and spaces, then it is rejected as "has no text"; 501 characters after cleaning is rejected; 500 is accepted.
- **ENG-TRAIN-007**: Given `validate_training_rows` with `max_rows=200` and 201 rows, then it raises; 200 passes; with `max_rows=2000`, 2001 raises.
- **ENG-TRAIN-008**: Given `dataset` rows with label `"attack"`, `"abc"` or `None`, then `"attack"` trains as `1` and the others raise `BoardValidationError` (never `ValueError`/`TypeError`).
- **ENG-TRAIN-009**: Given any allowlisted algorithm, when its pipeline is built, then the TF-IDF step has `max_features == 5000`.

### Model signing and evaluation (engine)

- **ENG-TRAIN-011**: Given a model signed with key K and context C, when `load_signed_model` is called with K and C, then the returned model's `predict_proba` matches the original's on sample texts.
- **ENG-TRAIN-012**: Given a signed blob, when it is loaded with a different key, a different context, one flipped payload byte, an unknown version byte or a truncated blob, then `ModelSignatureError` is raised and `pickle.loads` is never called (spied).
- **ENG-TRAIN-013**: Given an `ml_classifier` node with `model_id="m1"` and `ml_models={"m1": model}`, when `run_wave` evaluates it, then it routes by that model's probability and no fitting occurs (a spy on `fit_classifier` / `Pipeline.fit` records no call).
- **ENG-TRAIN-014**: Given an `ml_classifier` node whose `model_id` is absent from `ml_models` (or `ml_models` is `None`), then the hop detail is "Model not trained" and it routes `safe`.
- **ENG-TRAIN-015**: Given `strip_training_data(board)`, then every `ml_classifier` config has no `model_id` and no `dataset`, and all other node config is unchanged.
- **ENG-TRAIN-016**: Given every engine source file, when scanned, then no module references `os.environ`, `os.getenv` or `getenv(`, and the model-signing module calls no `open(` and imports no `redis`, `fastapi` or the gateway package; `sign_model` / `load_signed_model` take the key as a parameter.

### Training endpoint (API)

- **API-TRAIN-001**: Given no session cookie or an anonymous session, when `POST /game/train` is called with a valid dataset, then the answer is `403` "Sign in to train the ML filter." and no training runs.
- **API-TRAIN-002**: Given a signed-in free player, when they train successfully 3 times in one UTC day, then the 4th answers `429` and `GET /auth/session` reports `daily_train_limit=3`, `train_runs_used=3`.
- **API-TRAIN-003**: Given a signed-in free player, when a training answers `422` (bad label or oversized model) or `413`, then `train_runs_used` does not change; when it times out with `503`, `train_runs_used` increments by `1`.
- **API-TRAIN-005**: Given a campaign-mode request body over 131,072 bytes, then `413`; a paid custom-mode body of 1,000,000 bytes is accepted, and over 1,310,720 bytes is `413`.
- **API-TRAIN-006**: Given campaign mode with 201 rows, then `422`; a paid player with `level_id="custom"` and 2000 rows gets `200`; 2001 rows gets `422`.
- **API-TRAIN-007**: Given a free player sending `level_id="custom"`, then `403` "Custom mode is for paid players." and no training runs.
- **API-TRAIN-008**: Given `dataset` with an extra key, a non-string `text`, or label `"abc"`, then `422`, never `500`.
- **API-TRAIN-009**: Given a fake trainer that sleeps past `TRAIN_TIMEOUT_SECONDS` (small value via the container), when `/game/train` is called, then `503`, `train_runs_used` increments by `1`, and a concurrent `GET /health` completes before the training does.
- **API-TRAIN-033**: Given a free player (`daily_train_limit = 3`), when 8 concurrent valid `POST /game/train` requests arrive simultaneously on `InMemoryPlayerStore` or `SupabasePlayerStore`, then exactly 3 succeed (`200`), 5 fail with `429`, and `train_runs_used == 3`.
- **API-TRAIN-034**: Given default subprocess training with a child command that signals `{"ready": true}`, writes its PID, and sleeps past `TRAIN_TIMEOUT_SECONDS` on fit, when `POST /game/train` returns `503`, then the child process has been killed (`os.kill(pid, 0)` raises `ProcessLookupError`) and `train_runs_used == 1`.
- **API-TRAIN-036**: Given subprocess training via `TrainWorkerRunner`, consecutive valid `POST /game/train` calls reuse the same warm worker PID; a cold-start import delay before `{"ready": true}` does not count against `TRAIN_TIMEOUT_SECONDS`; and after a `503` fit timeout kills the stuck worker, the next `POST /game/train` spawns a new worker PID and succeeds (`200`).
- **API-TRAIN-035**: Given a signed-in player in `RedisTrainedModelStore` who trains a model and uses it on `/game/run` at intervals exceeding the 60-minute initial account-index TTL, when `purge_account` runs, then `mlmodels:acct:<sha256(email)>` has stayed alive and purges the active model.
- **API-TRAIN-012**: Given the generated OpenAPI contract, then `GameTrainRequest.dataset` items are a typed row schema, `GameTrainRequest` has `level_id` and no `replaces_model_id`, `GameTrainResponse` has `model_id` and `expires_at` and no `dataset`, `GameRunResponse` has `untrained_model_nodes`, and `PlayerSessionStatus` has `daily_train_limit` and `train_runs_used`.
- **API-TRAIN-013**: Given the Supabase (fake client) and in-memory players stores, when a free player trains, then `daily_usage.train_runs` for their email and today increments by 1.
- **API-TRAIN-014**: Given a signed-in paid player, when they train successfully 200 times in a UTC day (counter seeded to 199 in the store), then the 201st answers `429`; `GET /auth/session` reports `daily_train_limit=200`. Replaced by API-FAIR-008 (0050).
- **API-TRAIN-015**: Given a successful training, then the response has `model_id`, `sample_count`, `accuracy`, `expires_at` (≈ now + 1800 s) and no `dataset`, and the CSV text and rows appear in no store key or value, no log record (captured) and no file under the working directory or temp directory.
- **API-TRAIN-016**: Given a training whose signed blob exceeds `MODEL_MAX_BYTES` (1 MB), then `422` and not counted, and the session's earlier model (if any) is kept.
- **API-TRAIN-017**: Given `APP_ENV="production"` and no `MODEL_SIGNING_KEY`, then `/game/train` answers `503` "Training is unavailable." and creating the app logs an error; given `APP_ENV="development"` and no key, training works with a generated key.

### Model store and purge (API)

- **API-TRAIN-018**: Given a trained model, when `/game/run` uses its `model_id` in the same session, then the node routes by the model (not "Model not trained"), the model is not refit, and the store's TTL for it is reset to 1800 s.
- **API-TRAIN-019**: Given a trained model and a fake clock, when 1801 s pass with no run using it, then a run with that `model_id` reports the node in `untrained_model_nodes` and routes it as untrained.
- **API-TRAIN-030**: Given session A holds model `m1` (for node `ml_a`), when A trains successfully again (for `ml_a` or for another node `ml_b`), then `m1` is deleted, the store holds exactly one model for A (the new one), and a `/game/run` using `m1` reports that node untrained; session B's model is untouched.
- **API-TRAIN-031**: Given a board with two ML filter nodes, one holding the session's current `model_id` and one holding an older `model_id`, when `/game/run` runs, then only the first routes by the model and the second is listed in `untrained_model_nodes`.
- **API-TRAIN-032**: Given two concurrent successful trainings for one session (in-memory and fake Redis stores), then afterwards the store holds exactly one model for that session and the other `model_id` loads as untrained.
- **API-TRAIN-021**: Given a session with 2 models, when it calls `DELETE /game/models` (or `POST /game/models/purge`), then both are deleted and the answer is `204`; calling it again also answers `204`; another session's models are untouched.
- **API-TRAIN-022**: Given models owned by a session, when the player logs out, then they are deleted; given models in two sessions of one account, when another-sessions revoke (password change) or `DELETE /account` runs, then the affected sessions' models are deleted.
- **API-TRAIN-023**: Given session A's `model_id`, when session B runs a board with it, then the node is untrained for B and listed in `untrained_model_nodes`.
- **API-TRAIN-024**: Given a stored blob whose bytes were altered in the store, when `/game/run` loads it, then it is not unpickled (spied), the entry is deleted, a warning is logged, and the node is reported untrained.
- **API-TRAIN-025**: Given a Redis-backed store (fake async Redis), when container A stores a model and container B (same fake, same key) runs a board with that `model_id` for the same session, then B loads it; keys contain only hashes, never the raw session token or email.
- **API-TRAIN-026**: Given `POST /game/run` whose board has `config.dataset` on any node, then `422` "Training data is not accepted here. Train the ML filter first." and nothing is counted (anonymous and signed-in).

### Saves and scores (API)

- **API-TRAIN-027**: Given `PUT /game/saves/{level_id}` with an `ml_classifier` holding `model_id` and `dataset`, then the stored save has neither, and `GET` returns the board without them.
- **API-TRAIN-028**: Given an older save that still has `config.dataset`, when it is loaded with `GET /game/saves/{level_id}`, then the response has no `dataset` and no `model_id`.
- **API-TRAIN-029**: Given a recorded run whose board used a trained `model_id`, then the stored score's `board_json` has no `model_id` and no `dataset`.

### Web

- **WEB-TRAIN-001**: Given an anonymous session, when the ML filter settings open, then the Train button, file input and CSV textarea are disabled and a "Sign in to train" link to `/auth/login` is shown.
- **WEB-TRAIN-002**: Given `checkTrainingFile(file, mode)` (pure, `app/utils/`), when the file is larger than 131,072 bytes (campaign) or 1,310,720 bytes (custom), then it returns an error without reading the file.
- **WEB-TRAIN-003**: Given `decodeTrainingCsv(bytes)` with invalid UTF-8, then it returns "The file must be UTF-8 text."; valid UTF-8 returns the text.
- **WEB-TRAIN-004**: Given a free session with `daily_train_limit=3` and `train_runs_used=1`, then the ML filter shows "2 trainings left today".
- **WEB-TRAIN-005**: Given the training panel, then it shows the notice that the file is not stored and the model is deleted on leaving the game, after 30 minutes idle, or on retrain.
- **WEB-TRAIN-006**: Given a successful training response, when the node config is updated (pure helper), then it holds `model_id` and no `dataset`, and every other ML filter node on the board is marked "Retrain needed".
- **WEB-TRAIN-007**: Given a run response listing the node in `untrained_model_nodes`, or a freshly loaded saved board, then the ML filter shows "Retrain needed".
- **WEB-TRAIN-009**: Given a board where ML filter `ml_a` holds the session's model, when the player starts training ML filter `ml_b`, then a confirmation warns "Training this filter replaces your earlier trained model. The other ML filter will need a retrain." and cancelling sends no request; training `ml_a` again shows no warning.
- **WEB-TRAIN-008**: Given the game page, when the route is left, then `DELETE /game/models` is called once; when `pagehide` fires, then `navigator.sendBeacon` is called with `/api/v1/game/models/purge` (fakes for both).

### Retired IDs (never implemented)

- ENG-TRAIN-010 (validate `config.dataset` on `/run`): `/run` now rejects `config.dataset` outright (API-TRAIN-026).
- API-TRAIN-004 (paid has no daily cap): replaced by API-TRAIN-014 (200 a day).
- API-TRAIN-010 (row limits for `config.dataset` on `/run`): replaced by API-TRAIN-026.
- API-TRAIN-011 (validate `config.dataset` on saves): replaced by API-TRAIN-027/028 (stripped).
- API-TRAIN-020 (`replaces_model_id` deletes the named model): one model per session, user decision; replaced by API-TRAIN-030/031/032.
- The 10-models-per-session cap and its `409` (old API-TRAIN-016 second clause, `MODEL_MAX_PER_SESSION`): one model per session, user decision. API-TRAIN-016 now covers only `MODEL_MAX_BYTES`.

## Test changes

- Setup edits: the existing `/game/train` tests (API-GAME-006, API-ML-001,
  API-ML-002) sign in a free player first, and stop asserting the `dataset`
  echo; other assertions stay.
- Engine tests that train by putting `dataset` into `ml_classifier` config
  (ENG-GAME-006, ENG-GAME-007, ENG-ML-002, ENG-ML-003 in
  `packages/engine/tests/test_game.py`) switch to `fit_classifier` +
  `ml_models={model_id: model}`. What they check (routing on a trained or
  untrained filter, no pre-trained baseline) stays.
- Criteria text that named `config.dataset` (ENG-ML-003, API-ML-002 in spec
  0038; API-GAME-006 in spec 0016) was reworded to point here (user approved,
  2026-11-23); their status and Verification sections are unchanged.

## Security & privacy considerations

- Uploaded text is validated, fitted and dropped; it never reaches storage,
  logs, responses or disk. Only a signed model lives server-side, briefly.
- Pickles are loaded only after HMAC verification with a server secret, bound
  to the owner and `model_id` (AGENTS.md: never load unverified pickles). A
  Redis writer without the key cannot plant a loadable blob.
- `MODEL_SIGNING_KEY` is a server secret (never in the browser, never logged);
  production refuses to train without it.
- Models are per session: no cross-session or cross-account reuse; anonymous
  players cannot train or inject training data.
- CPU and storage are bounded by row, text and feature caps, a timeout, one
  model per session and the blob size.
- CSV export (out of scope) would need formula-injection escaping.
- Uploaded text is never sent to an LLM by this feature; if it ever is, it must
  go through `wrap_untrusted()`.

## Evaluation impact

`max_features=5000` can change a trained filter's scores on very large
datasets; campaign datasets are far below that. Record before/after easy-3
scores in `## Verification`. No change to the bundled baseline classifier.

- **easy-3 (`tfidf`, `safe_threshold=0.50`, `block_threshold=0.75`)**: before: `accuracy=1.0`, `total_score=9998`, `won=True`, `mastered=True`, `blocked=4/4`, `fa=0`; after (`max_features=5000`, pre-fitted once outside wave): `accuracy=1.0`, `total_score=10000`, `won=True`, `mastered=True`, `blocked=4/4`, `fa=0`.

## Open questions

None. Resolved 2026-11-23: one trained model per session (user decision);
`MODEL_MAX_BYTES` = 1 MB; specs 0016 and 0038 criteria reworded to point here.
No built-in level needs two trained ML filters at once: only easy-3 is
ML-focused and it teaches a single ML filter; no level constraint or test
solution uses two (the one engine test with two `ml_classifier` nodes uses two
separate one-node boards).

## Verification

### 2026-11-24 · commit faa585d (+ uncommitted changes)

- Criteria: ENG-TRAIN-001, ENG-TRAIN-002, ENG-TRAIN-003, ENG-TRAIN-004, ENG-TRAIN-005, ENG-TRAIN-006, ENG-TRAIN-007, ENG-TRAIN-008, ENG-TRAIN-009, ENG-TRAIN-011, ENG-TRAIN-012, ENG-TRAIN-013, ENG-TRAIN-014, ENG-TRAIN-015, ENG-TRAIN-016, API-TRAIN-001, API-TRAIN-002, API-TRAIN-003, API-TRAIN-005, API-TRAIN-006, API-TRAIN-007, API-TRAIN-008, API-TRAIN-009, API-TRAIN-012, API-TRAIN-013, API-TRAIN-014, API-TRAIN-015, API-TRAIN-016, API-TRAIN-017, API-TRAIN-018, API-TRAIN-019, API-TRAIN-030, API-TRAIN-031, API-TRAIN-032, API-TRAIN-021, API-TRAIN-022, API-TRAIN-023, API-TRAIN-024, API-TRAIN-025, API-TRAIN-026, API-TRAIN-027, API-TRAIN-028, API-TRAIN-029, WEB-TRAIN-001, WEB-TRAIN-002, WEB-TRAIN-003, WEB-TRAIN-004, WEB-TRAIN-005, WEB-TRAIN-006, WEB-TRAIN-007, WEB-TRAIN-009, WEB-TRAIN-008
- Red: 52 failing test(s) before implementation (`packages/engine/tests/test_train_hardening.py`, `packages/engine/tests/test_train_hardening.py`, `packages/engine/tests/test_train_hardening.py`)
- Green: 53 passing test(s)
- Gate: `mise run check` passed

### 2026-11-24 · commit faa585d (+ uncommitted changes)

- Criteria: API-TRAIN-003, API-TRAIN-009, API-TRAIN-033, API-TRAIN-034, API-TRAIN-035
- Red: 5 failing test(s) before implementation (`apps/api/tests/test_train_hardening_api.py::test_slow_training_times_out_with_503_without_blocking_health`, `apps/api/tests/test_train_hardening_api.py::test_slow_training_times_out_with_503_without_blocking_health`, `apps/api/tests/test_train_hardening_api.py::test_concurrent_train_requests_cannot_exceed_daily_limit`)
- Green: 6 passing test(s)
- Gate: `mise run check` passed

### 2026-11-24 · commit faa585d (+ uncommitted changes)

- Criteria: API-TRAIN-036
- Red: 1 failing test(s) before implementation (`apps/api/tests/test_train_hardening_api.py::test_warm_train_worker_reuses_process_isolates_cold_start_and_recovers_after_timeout`)
- Green: 1 passing test(s)
- Gate: `mise run check` passed
