-- The Agent review check kind is renamed to llm_review (one LLM call, no debate).
-- Rewrite stored boards so they still validate against the new NodeKind.

update game.saved_boards
set save_json = replace(save_json::text, '"agent_review"', '"llm_review"')::jsonb
where save_json::text like '%"agent_review"%';

update game.scores
set board_json = replace(board_json::text, '"agent_review"', '"llm_review"')::jsonb
where board_json::text like '%"agent_review"%';
