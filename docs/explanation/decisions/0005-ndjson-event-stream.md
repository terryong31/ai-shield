# 0005. NDJSON event stream for `/chat`

- **Status:** Accepted
- **Date:** 2026-09-23

## Context

The demo's value is showing the pipeline work: Layer 1 scoring, moderation,
each debate turn, the policy decision and tool calls, as they happen. A
request can take several seconds when Layer 2 runs, so a single JSON response
would leave the UI idle and then jump to the end.

The previous implementation streamed JSON objects separated by `"\n\n"`, used
mixed event naming (upper-case `START`, `ML_RESULT`, but lower-case
`debate_step` emitted from a different module), and had no schema, so the
client parsed events by convention.

Options considered:

- **Server-Sent Events**: a standard for server push, but browsers'
  `EventSource` supports only GET without a body, so a POST with a JSON prompt
  needs a custom SSE parser over `fetch` anyway, plus the `data:` framing.
- **WebSockets**: bidirectional, which this flow does not need, with extra
  infrastructure (upgrade handling, proxies, connection state).
- **Newline-delimited JSON over a streamed POST response**: one JSON document
  per line, readable with `fetch` and a line splitter, trivial to produce, test
  and inspect with `curl`.

## Decision

- `POST /api/v1/chat` returns `application/x-ndjson`: one JSON object per line,
  each terminated by a single `"\n"`, sent as soon as it is produced.
- Every event has a `type` discriminator in upper snake case. The set is
  closed and defined as a Pydantic discriminated union, `ChatEvent`, in
  `schemas.py`: `START`, `STAGE_CHANGE`, `ML_RESULT`, `LLAMAGUARD_RESULT`,
  `DEBATE_TURN`, `BLOCK`, `POLICY_UPDATE`, `TOOL_START`, `TOOL_END`,
  `FINAL_RESPONSE`, `ERROR`.
- The union is published in the OpenAPI contract (FastAPI cannot infer it from
  a stream, so `main.py` adds it), and the web client's types are generated from it.
- The old `"\n\n"` separator is normalised to `"\n"`, and the old lower-case
  `debate_step` event is renamed `DEBATE_TURN`.
- Failures inside the stream are reported as an `ERROR` event with a generic
  message; the HTTP status is already 200 once streaming starts.

## Consequences

- The client parser is small and pure (`splitNdjson`/`parseNdjson` in
  `app/utils/chatStream.ts`): split on `"\n"`, keep the trailing partial line,
  skip blank lines, report malformed lines without throwing. Blank-line
  tolerance means a stray `"\n\n"` does not produce empty events (WEB-STREAM-002).
- Event shapes are type-checked end to end and covered by contract tests
  (API-CONTRACT-001 checks the full set of event types).
- Clients written against the old stream must rename `debate_step` handling.
- There is no resume or replay: a dropped connection loses the rest of the stream.
- HTTP status codes cannot signal failures that happen mid-stream; clients must
  handle `ERROR` events.
