-- Spec 0051: the campaign has 19 levels. The four removed levels lose their saves and scores.
-- There are no players yet (owner decision, 2026-11-26).
delete from game.saved_boards where level_id in ('medium-8', 'medium-9', 'medium-10', 'hard-8');
delete from game.scores where level_id in ('medium-8', 'medium-9', 'medium-10', 'hard-8');
