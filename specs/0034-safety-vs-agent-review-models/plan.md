# Plan — 0034 Distinct Safety check vs Agent review

1. **Engine (`packages/engine/src/shield_engine/game/__init__.py`)**:
   - Validate `agent_review` `config.prompt` length (`<= 1000` chars) in `validate_board`.
   - Accept optional `check_model_for: Callable[[str], UsageChatModel | None] | None = None` on `evaluate_message`, `run_wave`, `run_single_message`, and `run_custom_wave` / `run_custom_message`.
   - In `safety_check`: support both JSON `{"flagged": bool}` and native guardrail plain-text outputs (`unsafe...`, `yes...`).
   - In `agent_review`: include player-configured `config.prompt` inside `<review_instructions>` in the system message sent to the LLM.
2. **API (`apps/api/src/shield_api/container.py` & `routers/game.py`)**:
   - Add `check_model_for(model_name)` helper in `container.py` (instantiating `GeminiChatModel` for `gemini-*` when `GOOGLE_API_KEY` is set and `GroqChatModel` for Groq/Llama/Qwen/ShieldGemma/Guard models when `GROQ_API_KEY` is set, falling back to `game_agent` / `game_agents`).
3. **Web (`apps/web/app/utils/gameBoard.ts` & `apps/web/app/pages/game.vue`)**:
   - Define distinct `SAFETY_CHECK_MODELS` (Llama Guard 3/4, Qwen3Guard, ShieldGemma, Nemotron Safety Guard) and `AGENT_REVIEW_MODELS` (Gemini 2.5/2.0 Flash, Llama 3.3 70B / 3.1 8B, GPT-4o mini) in `gameBoard.ts`.
   - Set defaults on new nodes: `safety_check` -> `model: 'llama-guard-3-8b'`; `agent_review` -> `model: 'gemini-2.5-flash'`, `prompt: ''`.
   - Replace the 4-button grid in `game.vue` with `<USelectMenu>` for both nodes, and add a `<UTextarea>` for `agent_review` review instructions (`config.prompt`).
