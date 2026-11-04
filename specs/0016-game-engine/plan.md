# 0016 Plan: Game engine

## Architecture

Add a `shield_engine/game/` subpackage inside `packages/engine/src/shield_engine/`:
- `types.py`: Frozen dataclasses `BoardNode`, `BoardEdge`, `BoardGraph`, `HopTrace`, `MessageTrace`, `LevelMessage`, `GameLevel`, `WaveScore`, `WaveResult`.
- `detectors.py`: `WordFilterDetector` (fast pattern groups) and `TextCleaner` (zero-width strip, base64 unpack, untrusted marker).
- `levels.py`: Built-in `easy`, `medium`, and `hard` levels with realistic normal user queries, tricky developer queries, and prompt injection attacks.
- `scoring.py`: Pure `score_wave` function implementing the 10,000-point formula and medal thresholds.
- `runner.py`: `validate_board`, `evaluate_message`, and `run_wave` supporting both offline deterministic execution and custom live LLM ports.
