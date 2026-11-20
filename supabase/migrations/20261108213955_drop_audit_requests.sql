-- Spec 0026: the repository is game-only. The chat request audit log
-- (`audit.requests`, which stored user prompts) has no writer any more, so it
-- is dropped together with its rows. Back the table up first if you need them.
-- The `audit` schema stays: it still holds `audit.clearance_sessions`.

drop table if exists audit.requests;
