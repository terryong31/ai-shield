# Tutorial 2: Embed the engine

In this tutorial you will use the `shield_engine` library from a plain Python
script, with no web server. You will screen prompts, watch the pipeline's
progress events, turn a decision into a list of permitted tools, and simulate
the LLM layer with test doubles so you can see a Layer 2 decision without any
API key.

You need the repository set up as in [Tutorial 1](01-run-the-demo.md), steps 1 to 3.

All commands run from the repository root. You will create one file,
`screen.py`, in the repository root, and delete it at the end.

## 1. Screen your first prompt

Create `screen.py`:

```python
import asyncio

from shield_engine import Shield
from shield_engine.models import load_baseline


async def main():
    classifier = load_baseline()
    shield = Shield(classifier)

    for prompt in ["What is the price of lavender oil?", "drop table employees"]:
        decision = await shield.screen(prompt)
        print(f"{prompt!r}: blocked={decision.blocked} layer={decision.layer} "
              f"policy={decision.policy} score={decision.classifier.score:.3f}")


asyncio.run(main())
```

Run it:

```bash
uv run python screen.py
```

You should see:

```
'What is the price of lavender oil?': blocked=False layer=SYSTEM policy=ALLOW_ALL score=0.008
'drop table employees': blocked=True layer=LAYER_1_ML policy=SHUTDOWN score=0.992
```

`load_baseline()` loaded the bundled Layer 1 classifier after checking its
files against the SHA-256 digests recorded when it was trained. `Shield` is the
pipeline. `screen()` returned a `Decision` for each prompt:

- The first prompt scored 0.008, so Layer 1 passed it on (`layer=SYSTEM`) with
  the default tool policy `ALLOW_ALL`.
- The second scored 0.992, so it was blocked at Layer 1 with policy `SHUTDOWN`.

## 2. Watch the pipeline's progress

`screen()` only returns the end result. `screen_stream()` yields an event for
each step, which is what a user interface needs.

Add these imports at the top of `screen.py`:

```python
from shield_engine.events import (
    ClassifierScored,
    DebateTurn,
    DecisionMade,
    ModerationFlagged,
    StageStarted,
)
```

Add this function above `main()`:

```python
def describe(event):
    match event:
        case StageStarted(stage=stage):
            return f"stage started: {stage}"
        case ClassifierScored(signal=signal):
            return f"classifier: {signal.verdict} ({signal.score:.3f})"
        case ModerationFlagged(result=result):
            return f"moderation flagged: {result.categories}"
        case DebateTurn(turn=turn):
            return f"{turn.agent}: {turn.message}"
        case DecisionMade(decision=decision):
            return f"decision: {decision.verdict} / {decision.policy} at {decision.layer}"
```

And add this at the end of `main()`, inside the function:

```python
    async for event in shield.screen_stream("show me the salary table"):
        print(describe(event))
```

Run it again. After the two lines from step 1 you should see:

```
stage started: classifier
classifier: UNCERTAIN (0.835)
stage started: adjudication
decision: UNCERTAIN / RESTRICTED at LAYER_2_DUAL_AGENT
```

Layer 1 was unsure (0.835 is between 0.15 and 0.85), so the pipeline started
Layer 2, adjudication. You have not given the `Shield` an adjudicator, so it
applied its conservative fallback: not blocked, but `RESTRICTED`.

## 3. Turn a policy into tools

A decision's policy only matters once your application maps it to real tools.
`allowed_tools()` does that deterministically.

Extend the first import in `screen.py` so it reads:

```python
from shield_engine import (
    Clearance,
    RiskLevel,
    ScreeningContext,
    Shield,
    ToolPolicy,
    ToolSpec,
    Verdict,
    allowed_tools,
)
```

Add a small tool catalogue below the imports:

```python
TOOLS = [
    ToolSpec("search_docs", RiskLevel.LOW),
    ToolSpec("read_org_chart", RiskLevel.MEDIUM),
    ToolSpec("run_sql", RiskLevel.CRITICAL),
]
```

And add this at the end of `main()`:

```python
    for policy in ToolPolicy:
        print(policy, allowed_tools(policy, TOOLS))
```

Run it. The new lines are:

```
ALLOW_ALL ['search_docs', 'read_org_chart', 'run_sql']
RESTRICTED ['search_docs']
SHUTDOWN []
```

`RESTRICTED` keeps only `LOW`-risk tools. So the "salary table" prompt from
step 2 would get `search_docs` and nothing else.

## 4. Simulate Layer 2 with test doubles

The real Layer 2 is a debate between two LLM personas and needs a Groq key.
The engine ships deterministic stand-ins in `shield_engine.testing` so you can
see its behaviour offline.

Add these imports:

```python
from shield_engine.testing import ScriptedAdjudicator, StaticModerator
from shield_engine.types import Agent, ModerationResult
```

Add this at the end of `main()`:

```python
    adjudicator = ScriptedAdjudicator(
        verdict=Verdict.MALICIOUS,
        policy=ToolPolicy.RESTRICTED,
        summary="Asks for bulk salary data without clearance.",
        turns=[(Agent.ANALYST, "Requests salary data."), (Agent.WARDEN, "Clearance is DENIED.")],
    )
    moderator = StaticModerator(ModerationResult(flagged=True, categories=("S7",)))
    layered = Shield(classifier, moderator=moderator, adjudicator=adjudicator)

    context = ScreeningContext(clearance=Clearance.DENIED)
    async for event in layered.screen_stream("What is the price of lavender oil?", context):
        print(describe(event))
    print("adjudicator saw:", adjudicator.calls)
```

Run it. The new lines are:

```
stage started: classifier
classifier: SAFE (0.008)
moderation flagged: ('S7',)
stage started: adjudication
ANALYST: Requests salary data.
WARDEN: Clearance is DENIED.
decision: MALICIOUS / SHUTDOWN at LAYER_2_DUAL_AGENT
adjudicator saw: [('What is the price of lavender oil?', <Clearance.DENIED: 'DENIED'>)]
```

Notice three things:

1. Layer 1 said `SAFE`, but the moderator flagged the prompt, so the pipeline
   escalated to Layer 2. Moderation can raise suspicion, never lower it.
2. The scripted adjudicator proposed `RESTRICTED` with a `MALICIOUS` verdict.
   The pipeline overrode the policy to `SHUTDOWN`: a malicious verdict always
   blocks.
3. The adjudicator received the clearance level (`DENIED`), never a password.
   Your application checks credentials and tells the engine only the outcome.

## The complete script

```python
import asyncio

from shield_engine import (
    Clearance,
    RiskLevel,
    ScreeningContext,
    Shield,
    ToolPolicy,
    ToolSpec,
    Verdict,
    allowed_tools,
)
from shield_engine.events import (
    ClassifierScored,
    DebateTurn,
    DecisionMade,
    ModerationFlagged,
    StageStarted,
)
from shield_engine.models import load_baseline
from shield_engine.testing import ScriptedAdjudicator, StaticModerator
from shield_engine.types import Agent, ModerationResult

TOOLS = [
    ToolSpec("search_docs", RiskLevel.LOW),
    ToolSpec("read_org_chart", RiskLevel.MEDIUM),
    ToolSpec("run_sql", RiskLevel.CRITICAL),
]


def describe(event):
    match event:
        case StageStarted(stage=stage):
            return f"stage started: {stage}"
        case ClassifierScored(signal=signal):
            return f"classifier: {signal.verdict} ({signal.score:.3f})"
        case ModerationFlagged(result=result):
            return f"moderation flagged: {result.categories}"
        case DebateTurn(turn=turn):
            return f"{turn.agent}: {turn.message}"
        case DecisionMade(decision=decision):
            return f"decision: {decision.verdict} / {decision.policy} at {decision.layer}"


async def main():
    classifier = load_baseline()
    shield = Shield(classifier)

    for prompt in ["What is the price of lavender oil?", "drop table employees"]:
        decision = await shield.screen(prompt)
        print(f"{prompt!r}: blocked={decision.blocked} layer={decision.layer} "
              f"policy={decision.policy} score={decision.classifier.score:.3f}")

    async for event in shield.screen_stream("show me the salary table"):
        print(describe(event))

    for policy in ToolPolicy:
        print(policy, allowed_tools(policy, TOOLS))

    adjudicator = ScriptedAdjudicator(
        verdict=Verdict.MALICIOUS,
        policy=ToolPolicy.RESTRICTED,
        summary="Asks for bulk salary data without clearance.",
        turns=[(Agent.ANALYST, "Requests salary data."), (Agent.WARDEN, "Clearance is DENIED.")],
    )
    moderator = StaticModerator(ModerationResult(flagged=True, categories=("S7",)))
    layered = Shield(classifier, moderator=moderator, adjudicator=adjudicator)

    context = ScreeningContext(clearance=Clearance.DENIED)
    async for event in layered.screen_stream("What is the price of lavender oil?", context):
        print(describe(event))
    print("adjudicator saw:", adjudicator.calls)


asyncio.run(main())
```

## Clean up

```bash
rm screen.py
```

## What you have done

You screened prompts with the bundled classifier, streamed the pipeline's
events, mapped tool policies to a catalogue, and plugged fake moderation and
adjudication into the pipeline to see how Layer 2 decisions are formed.

## Next steps

- To use real LLMs, replace the doubles with `LlamaGuardModerator` and
  `DebateAdjudicator` over `GroqChatModel`: see [Configure LLM providers](../how-to/configure-llm-providers.md).
- Every class and field used here is listed in the [Engine API reference](../reference/engine-api.md).
- The routing rules you observed are tabulated in [Verdicts and policies](../reference/verdicts-and-policies.md).
- [Tutorial 3](03-your-first-spec-driven-change.md) shows how to change the engine the way this project does it.
