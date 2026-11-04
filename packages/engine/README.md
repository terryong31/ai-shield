# shield-engine

The `ai-shield` prompt-injection deflector and workflow defence game engine as a standalone Python library.
It has no web framework, database or provider SDK in its core dependencies:
you inject those through small ports.

```
prompt ─▶ Layer 1 classifier ─▶ moderation (optional) ─▶ Layer 2 debate (when needed) ─▶ Decision
```

A `Decision` tells the host application whether to block the prompt and
which **tool policy** (`ALLOW_ALL`, `RESTRICTED`, `SHUTDOWN`) applies if it proceeds.

## Install

```bash
uv add shield-engine            # core
uv add 'shield-engine[groq]'    # + Groq adapter for moderation and debate
```

Inside this monorepo it is a uv workspace member; `mise run setup` installs it.

## Use

```python
import asyncio
from shield_engine import Clearance, ScreeningContext, Shield, allowed_tools
from shield_engine.models import load_baseline

shield = Shield(load_baseline())

decision = asyncio.run(shield.screen("drop table employees", ScreeningContext(Clearance.NONE)))
print(decision.blocked, decision.layer, decision.reason)
```

Stream progress events instead (for UIs):

```python
async for event in shield.screen_stream(prompt, context):
    ...  # StageStarted, ClassifierScored, ModerationFlagged, DebateTurn, DecisionMade
```

Add the LLM layers:

```python
from shield_engine import DebateAdjudicator, LlamaGuardModerator
from shield_engine.adapters.groq import GroqChatModel

shield = Shield(
    load_baseline(),
    moderator=LlamaGuardModerator(GroqChatModel(key, "llama-guard-3-8b")),
    adjudicator=DebateAdjudicator(GroqChatModel(key, "llama-3.3-70b-versatile")),
)
```

## CLI

```bash
shield-engine eval  --data data/seed/eval.jsonl --report reports/baseline.json
shield-engine train --data data/seed/train.jsonl
```

## Documentation

- Tutorial: [Screen your first prompt](../../docs/tutorials/02-embed-the-engine.md)
- Reference: [Engine API](../../docs/reference/engine-api.md)
- Explanation: [Defense in depth](../../docs/explanation/defense-in-depth.md)
- [Model card](MODEL_CARD.md)
- Specs: `specs/0001`–`0006`
