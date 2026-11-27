# 0057 — k6 load testing: tasks

Run as one SDD cycle. `mise run sdd:done` ticks the criterion lines automatically.

- [ ] `mise run sdd:start 0057`
- [ ] Confirm adding pinned `k6` tool to `mise.toml` and creating `.github/workflows/load.yml`
- [x] **DEV-LOAD-001**: write failing test
- [x] **DEV-LOAD-002**: write failing test
- [x] **DEV-LOAD-003**: write failing test
- [x] **DEV-LOAD-004**: write failing test
- [x] **DEV-LOAD-005**: write failing test
- [x] **DEV-LOAD-006**: write failing test
- [x] **DEV-LOAD-007**: write failing test
- [ ] `mise run sdd:red` accepted
- [ ] Implement `perf/k6/` library and scenarios, `mise.toml` `perf:*` tasks, `.gitignore`, and `.github/workflows/load.yml`; `mise run sdd:green` accepted
- [ ] Update docs (`docs/how-to/` and `docs/reference/`) and `CHANGELOG.md`
- [ ] `mise run sdd:verify`, then `mise run sdd:done`
