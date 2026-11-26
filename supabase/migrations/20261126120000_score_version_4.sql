-- Spec 0050: the campaign score formula changed, so version 4 starts an empty leaderboard.
-- There are no players yet (owner decision, 2026-11-26), so earlier rows are deleted.
delete from game.scores where score_version < 4;
