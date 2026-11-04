# 0017 Tasks: Game gateway API and scoreboard storage

- [ ] **API-GAME-001** Add `GET /api/v1/game/levels` endpoint
- [ ] **API-GAME-002** Add `POST /api/v1/game/run` wave evaluation and board validation
- [ ] **API-GAME-003** Support `custom_message` red-team test in `POST /api/v1/game/run`
- [ ] **API-GAME-004** Persist and query high scores in SQLite via `POST` and `GET /api/v1/game/scores`
- [ ] **API-GAME-005** Guard `DELETE /api/v1/game/scores` behind admin clearance session
