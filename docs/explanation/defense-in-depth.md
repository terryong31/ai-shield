# Defense in depth

No single detector stops prompt injection. Classifiers miss paraphrases, LLM
judges can themselves be injected, and keyword rules are easy to evade. AI
S.H.I.E.L.D. stacks several different kinds of check so that an attack has to
beat all of them, and puts the final say in plain code.

```
prompt ─▶ L1 classifier ─▶ moderation ─▶ L2 debate (when needed) ─▶ policy gate ─▶ tools
          cheap, local      independent   contextual, expensive      deterministic
          deterministic     can only      LLM reasoning              outside any LLM
                            escalate
```

## Why this order

**Layer 1: a local classifier.** A TF-IDF + logistic-loss SGD model scores the
prompt in about a tenth of a millisecond, offline, with the same answer every
time. It is weak (see the [model card](../../packages/engine/MODEL_CARD.md)),
but it is cheap enough to run on everything and good at blatant attacks. Its
two thresholds split prompts three ways: clear attacks are blocked here and
never cost an LLM call; clearly benign prompts pass; the rest are routed on.
Being wrong in the middle is acceptable because the middle goes to Layer 2.

A sensitive-keyword floor adds a bias toward review: low scores on prompts
that mention salaries, databases, tables and similar nouns are raised into the
uncertain band. This trades cost (more Layer 2 calls) for fewer quiet misses in
the areas where damage would be greatest.

**Moderation: an independent opinion.** Llama Guard was trained on a different
problem (a hazard taxonomy: violence, cyberattacks, privacy) by different
people on different data. Its errors are unlikely to line up with the
classifier's. It is only allowed to *escalate*: a flag turns SAFE into
UNCERTAIN, sending the prompt to Layer 2; it never turns a MALICIOUS verdict
into anything milder. Because it cannot relax anything, a broken or fooled
moderator can at worst waste a Layer 2 call.

**Layer 2: contextual reasoning.** Uncertain prompts go to a debate between two
LLM personas, the Analyst (what is this prompt trying to do?) and the Warden
(what does policy allow for this caller?), ending with a binding JSON verdict
and tool policy. This is the only layer that understands intent and context,
and the most expensive and least predictable one, so it only runs when needed.

**The policy gate: deterministic enforcement.** Whatever the layers decide is
reduced to one of three policies, and `allowed_tools()` maps that to concrete
tools by risk label. This step is ordinary code.

## Why the policy gate sits outside any LLM

Layer 2 reads attacker-controlled text. The prompt is wrapped in
`<untrusted_prompt>` tags, look-alike tags are neutralised, and the models are
told to treat the content as data, but delimiting reduces injection risk
rather than removing it. Assume that sometimes an attacker will talk the
Warden into a lenient verdict.

The gate limits what that buys them:

- A `MALICIOUS` verdict always becomes `SHUTDOWN`, whatever policy the Warden proposed.
- The most an injected Warden can grant is its own output vocabulary. `RESTRICTED`
  still means LOW-risk tools only, enforced by code that no prompt can reach.
- The risk labels are data the host controls. The demo's labels are pinned by a
  test (`API-TOOLS-001`), because a mislabelled tool is a hole in the gate: the
  original demo rated `drop_database_table` as LOW and so left it available
  under `RESTRICTED`.
- The assistant only receives the permitted tool names. There is no path by
  which the assistant can call an unlisted tool.

In short, LLMs advise; code decides what is reachable.

## Failure modes: fail-open, fail-closed, fail-restricted

Each component has an explicit answer to "what happens when this breaks?"

| Component | On failure | Rationale |
| --- | --- | --- |
| Classifier artifacts | **Fail closed**: `ArtifactIntegrityError`, the gateway does not start | A tampered pickle is code execution; better no service than a compromised one |
| Moderation (provider error) | **Fail open** by default (`fail_closed=False`): not flagged, error recorded | Moderation can only escalate, so failing open cannot allow anything by itself; it removes one signal. Configurable for deployments that rely on it |
| Layer 2 (provider error, bad JSON, no adjudicator) | **Fail restricted**: UNCERTAIN + `RESTRICTED` (cleared callers: SAFE + `ALLOW_ALL`) | Blocking would make every provider outage a total outage for ambiguous prompts; allowing everything would make an outage an attack window. Restricting keeps the service useful for low-risk work while removing dangerous tools |
| Audit writes | **Fail open**: logged, request continues | Losing a log row should not break the user's request (but see the threat model) |
| Stream errors | Generic `ERROR` event | No internal detail reaches the client |

The fallback never blocks. Layer 1 has already had its chance to block, and a
Layer 2 outage is not evidence that a prompt is malicious.

## What the layers do not cover

- **Default policy for SAFE prompts.** Prompts Layer 1 passes without review get
  `default_policy`, which is `ALLOW_ALL` to preserve the original demo. A
  classifier miss therefore means full tool access. Deployments that want
  deny-by-default should set `default_policy=RESTRICTED`, at the cost of
  sending more traffic to Layer 2 or restricting benign users.
- **Indirect injection.** The engine screens the user's prompt. Instructions
  hidden in documents or tool results that reach the assistant later are not
  screened.
- **Output checks.** Nothing inspects the assistant's answer.

These are tracked in the [threat model](threat-model.md).

## Related

- [Verdicts and policies](../reference/verdicts-and-policies.md) for the exact routing table
- [Architecture](architecture.md)
