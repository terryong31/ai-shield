# Tasks — 0030 Tool refinements and Jev

- [ ] Human review & mark `specs/0030-tool-refinements-and-jev/spec.md` as `Accepted`
- [ ] `mise run sdd:start 0030`
- [x] **ENG-TOOL-006** `text_cleanup` requires explicit `transforms` (`strip_zero_width`, `decode_base64`, `decode_hex_url`) and scales latency per enabled transform
- [x] **ENG-TOOL-007** `secret_scan` evaluates `patterns` as case-insensitive regular expressions and `validate_board` rejects invalid regexes
- [x] **ENG-TOOL-008** `tool_filter` evaluates per-tool `rules` (`always` or `match` regex) and blocks the Protected Agent from calling tools gated by `always` rules
- [x] **ENG-TOOL-009** `jev` System One decision node evaluates a player-written boolean `noul` question against `threshold` in `12.0 ms` at `$0.00005`
- [x] **API-TOOL-001** Expose `jev` in `/api/v1/game/levels`, validate regex/question configs on `/api/v1/game/run`, and regenerate OpenAPI contract + web types
- [x] **WEB-TOOL-001** Add `jev` to `NODE_CATALOG` and `/game`, and build modal configuration UIs for `text_cleanup` transforms, `secret_scan` regexes, `tool_filter` tool conditions, and `jev` `noul` question + threshold
