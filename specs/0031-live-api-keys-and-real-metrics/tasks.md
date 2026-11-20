# Tasks — 0031 Live Jev & AI node API keys and real measured latency/cost

- [ ] Human review & mark `specs/0031-live-api-keys-and-real-metrics/spec.md` as `Accepted`
- [ ] `mise run sdd:start 0031`
- [x] **ENG-LIVE-001** `jev` node requires `jev_client`, calls `evaluate_noul`, and records real measured `latency_ms` and token `cost_usd`
- [x] **ENG-LIVE-002** `safety_check` and `agent_review` require `check_model`, call `complete_with_usage` with `wrap_untrusted`, and record real measured `latency_ms` and token `cost_usd`
- [x] **ENG-LIVE-003** Every hop in `evaluate_message` records real backend elapsed `latency_ms` via `time.perf_counter()`
- [x] **API-LIVE-001** Expose `jev_key_configured` and `ai_key_configured` on `/api/v1/game/levels` and accept `jev_api_key` / `ai_api_key` on `/api/v1/game/run`
- [x] **WEB-LIVE-001** Disable `jev` with `"Insert Jev API key to continue"` and AI nodes with `"Enter API key to continue"` when no key is detected, with UI inputs to provide keys and real backend metrics display
