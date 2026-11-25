# shield-engine

The check library behind the `ai-shield` prompt-injection defence game: a
framework-free Python package that evaluates a player's board of checks against
a level's wave of prompts, runs the protected AI agent, and scores the run.

```
board + level ─▶ checks (word filter, length limit, secret scan, ML filter …)
             ─▶ final node (Help Desk, or the Protected Agent on a real or offline model)
             ─▶ traces + WaveScore (protection, helpfulness, tools, tokens, speed, cost)
```

## Install

```bash
uv add shield-engine            # core: scikit-learn + joblib
uv add 'shield-engine[groq]'    # + Groq adapter for the agent
```

## Use

```python
from shield_engine.game import BoardGraph, BoardNode, BoardEdge, run_wave
from shield_engine.models import load_baseline

board = BoardGraph(
    nodes=(
        BoardNode("incoming", "incoming"),
        BoardNode("screen", "word_filter", {"custom_words": ["ignore previous instructions"]}),
        BoardNode("assistant", "assistant"),
    ),
    edges=(
        BoardEdge("e1", "incoming", "out", "screen"),
        BoardEdge("e2", "screen", "safe", "assistant"),
    ),
)
result = await run_wave(board, level_id="easy-1", classifier=load_baseline())
result.score.total_score, result.score.medal
```

Agent levels take a `UsageChatModel` per tier (`agents={"standard": …, "budget": …}`);
without one they run a deterministic offline stand-in.

## Retrain the baseline

```bash
shield-engine train --data data/seed/train.jsonl   # or: mise run train
```

## Docs

- Reference: [Engine API](../../docs/reference/engine-api.md)
- How-to: [Retrain the classifier](../../docs/how-to/retrain-the-classifier.md)
- [Model card](MODEL_CARD.md)
