# Plan — 0030 Tool refinements and Jev

## Engine (`packages/engine`)

1. **`packages/engine/src/shield_engine/game/__init__.py`**:
   - Add `"jev"` to `NodeKind`, `VALID_NODE_KINDS`, and `CHECK_CATALOG` (`12.0 ms`, `$0.00005`, `handles=("safe",)`).
   - Update `TextCleaner`:
     - Accept `transforms: tuple[str, ...] | list[str] = ("strip_zero_width", "decode_base64")` on `TextCleaner.__init__` for direct class callers, while in `evaluate_message` read `node.config.get("transforms")` — if `transforms` is a list in `node.config`, use it (and default new nodes in `gameBoard.ts` to `transforms: []`; if `transforms` is not in `node.config` at all, wait: `ENG-TOOL-006` specifies `transforms=[]` or unconfigured `node.config`!). Let's check: if `raw_transforms = node.config.get("transforms")` is a list, use `tuple(raw_transforms)`; if omitted (`None`), default to `()` unless legacy? Wait: let's check existing tests in `test_game.py` (`ENG-GAME-003`, `ENG-GAME-006`) where `BoardNode(id="clean", kind="text_cleanup")` has `config={}`!
     - Hold on! In `test_game.py`:
       - `ENG-GAME-002` calls `TextCleaner().clean(...)` directly.
       - `ENG-GAME-006` (`test_cascading_branch_board_beats_all_agent_review_board_on_medium`) has `BoardNode(id="clean", kind="text_cleanup")`!
       - If `node.config.get("transforms")` defaults to `()` when `transforms` is `[]` (or when `config` is `{}`), wait: in `ENG-GAME-006`, why did `cascading_board` beat `all_llm_board` on Medium? Because `m7` is Base64 (`_M7_B64`), and in `_score_quick_screen`, if `cleaned` is `True` (or if `m7` is unpacked), `quick_screen` sends `m7` to `suspicious` (`0.62`) or blocks it (`0.91`), whereas if `m7` is NOT unpacked (`transforms=[]`), `m7` goes `safe` -> `assistant`, and on Medium (`standard` tier), `simulate_agent` resists `m7`? Wait: does `simulate_agent(tier="standard")` resist `m7` when `m7` is still base64-encoded?
       Let's check `packages/engine/src/shield_engine/game/agent.py`!
   - Update `secret_scan`: compile regexes in `validate_board` and match with `re.search(pattern, working_text, re.IGNORECASE)`.
   - Update `tool_filter`: support `config.rules` (`[{tool, condition: "always" | "match", pattern}]`) as well as `config.blocked_tools`, validate regexes in `validate_board`, and pass `blocked_tools: frozenset[str]` to `assistant` evaluation so blocked tools cannot be called by the agent.
   - Implement `_score_jev_noul(text: str, *, question: str, cleaned: bool, classifier: Classifier) -> float` and `node.kind == "jev"` evaluation.

## API (`apps/api`)

2. **`apps/api/src/shield_api/services/players.py`** & **`apps/api/src/shield_api/schemas.py`**:
   - Ensure `"jev"` is in `NodeKind` schema, and regenerate OpenAPI contract + web types via `mise run contract`.

## Web (`apps/web`)

3. **`apps/web/app/utils/gameBoard.ts`** & **`apps/web/app/pages/game.vue`**:
   - Add `jev` to `NODE_CATALOG` and `toolKinds`.
   - Set `defaultConfig.transforms = []` on `text_cleanup`, `defaultConfig.rules = []` on `tool_filter`, and `defaultConfig.question = ''`, `defaultConfig.threshold = 0.7` on `jev`.
   - Add modal config sections for:
     - `text_cleanup`: toggle buttons for `Strip zero-width chars`, `Decode Base64`, `Decode hex and URL` with live latency preview.
     - `secret_scan`: regex pattern input and list.
     - `tool_filter`: rule builder selecting a tool from the level's agent tools + condition (`Always block` vs `When prompt matches regex`) + regex input.
     - `jev`: `noul` boolean question input + probability threshold input.
