# Verdicts, policies and routing

How `Shield` turns layer outputs into a `Decision`. Source:
[`pipeline.py`](../../packages/engine/src/shield_engine/pipeline.py),
[`policy.py`](../../packages/engine/src/shield_engine/policy.py),
[`adjudication/fallback.py`](../../packages/engine/src/shield_engine/adjudication/fallback.py).
Specs: [0001](../../specs/0001-screening-pipeline/spec.md),
[0005](../../specs/0005-tool-policy/spec.md).

## Enums

### `Verdict`

| Value | Meaning |
| --- | --- |
| `SAFE` | The layer considers the prompt benign |
| `UNCERTAIN` | Not confident either way; routed to Layer 2, or allowed under a restricted policy |
| `MALICIOUS` | Blocked |

### `ToolPolicy`

| Value | Tools the host may expose |
| --- | --- |
| `ALLOW_ALL` | Every tool in the catalogue |
| `RESTRICTED` | Only tools with `RiskLevel.LOW` |
| `SHUTDOWN` | None. Always paired with `blocked=True` |

### `RiskLevel`

`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. Assigned by the host to each `ToolSpec`.
Only `LOW` survives `RESTRICTED`; `MEDIUM`, `HIGH` and `CRITICAL` are treated the same.

### `Clearance`

| Value | Set by the host when |
| --- | --- |
| `NONE` | The caller claimed no privileges |
| `DENIED` | The caller claimed privileges that did not verify |
| `GRANTED` | The caller's privileges verified |

In the demo gateway: no passphrase gives `NONE`; a passphrase equal to
`SECURE_PASSPHRASE` gives `GRANTED`; any other passphrase, or any passphrase
when `SECURE_PASSPHRASE` is unset, gives `DENIED`
([`services/access.py`](../../apps/api/src/shield_api/services/access.py)).

### `DecisionLayer`

| Member | Value (as stored in the audit log) | Produced when |
| --- | --- | --- |
| `CLASSIFIER` | `LAYER_1_ML` | Layer 1 (after moderation) routed `MALICIOUS` |
| `ADJUDICATION` | `LAYER_2_DUAL_AGENT` | Layer 2 ran, including the fallback |
| `PASSTHROUGH` | `SYSTEM` | No adjudication was needed |

## Classifier thresholds

`ClassifierDetector` defaults (configurable per instance):

| Probability `p` | Verdict |
| --- | --- |
| exact feedback label exists | label 1: `MALICIOUS` (score 1.0), label 0: `SAFE` (score 0.0), `override=True` |
| `p >= 0.85` | `MALICIOUS` |
| `p <= 0.15` | `SAFE` |
| otherwise | `UNCERTAIN` |

Before thresholding, `p < 0.35` on text containing a sensitive keyword is raised
to `0.40`, which is always `UNCERTAIN` with default thresholds.

## Routing table

Step 1: the **routed verdict** starts as the classifier verdict (or `SAFE` when
`skip_classifier=True`). If a moderator is configured and flags the prompt, a
`SAFE` or `UNCERTAIN` routed verdict becomes `UNCERTAIN`; `MALICIOUS` stays
`MALICIOUS`. Moderation never lowers a verdict.

Step 2: route.

| Routed verdict | `always_adjudicate` | Clearance | Adjudicator | Decision verdict | Policy | Blocked | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MALICIOUS` | any | any | any (not called) | `MALICIOUS` | `SHUTDOWN` | yes | `LAYER_1_ML` |
| `SAFE` | `False` | `NONE` | any (not called) | `SAFE` | `default_policy` (`ALLOW_ALL`) | no | `SYSTEM` |
| `SAFE` | `True` | any | configured | Layer 2 | see below | | `LAYER_2_DUAL_AGENT` |
| `SAFE` | any | `GRANTED`/`DENIED` | configured | Layer 2 | see below | | `LAYER_2_DUAL_AGENT` |
| `UNCERTAIN` | any | any | configured | Layer 2 | see below | | `LAYER_2_DUAL_AGENT` |
| needs Layer 2 | | `GRANTED` | none | `SAFE` | `ALLOW_ALL` | no | `LAYER_2_DUAL_AGENT` |
| needs Layer 2 | | `NONE`/`DENIED` | none | `UNCERTAIN` | `RESTRICTED` | no | `LAYER_2_DUAL_AGENT` |

"Needs Layer 2" means: routed verdict is `UNCERTAIN`, or `always_adjudicate` is
set, or clearance is not `NONE`.

When Layer 2 runs, the `Adjudication` decides:

| Adjudication verdict | Decision policy | Blocked |
| --- | --- | --- |
| `MALICIOUS` | `SHUTDOWN` (the proposed policy is ignored) | yes |
| `SAFE` or `UNCERTAIN` | the adjudication's `policy` | no |

`Decision.reason` is `"High confidence ML threat detection"` for Layer 1 blocks,
`"Passed Layer 1 screening"` for passthrough, and the adjudication `summary`
otherwise.

## Layer 2 fallback

`DebateAdjudicator` falls back when a model call raises or the Warden's JSON is
unusable. `Shield` uses the same fallback when no adjudicator is configured.

| Clearance | Verdict | Policy | Confidence | `fallback` |
| --- | --- | --- | --- | --- |
| `GRANTED` | `SAFE` | `ALLOW_ALL` | 0.5 | `True` |
| `NONE`, `DENIED` | `UNCERTAIN` | `RESTRICTED` | 0.5 | `True` |

## Policy gate: `RESTRICTED` allows `LOW` only

`allowed_tools(policy, tools)` is plain code, applied by the host after the
decision:

| Policy | Result |
| --- | --- |
| `ALLOW_ALL` | all tool names, catalogue order |
| `RESTRICTED` | names of tools whose `risk is RiskLevel.LOW`, catalogue order |
| `SHUTDOWN` | `[]` |

Demo catalogue ([`demo/tools.py`](../../apps/api/src/shield_api/demo/tools.py)):

| Tool | Risk | Allowed under `RESTRICTED` |
| --- | --- | --- |
| `search_documents` | `LOW` | yes |
| `search_quotations` | `LOW` | yes |
| `get_org_chart` | `MEDIUM` | no |
| `query_sales_database` | `HIGH` | no |
| `get_employee_data` | `HIGH` | no |
| `send_email` | `HIGH` | no |
| `export_data` | `HIGH` | no |
| `execute_sql` | `CRITICAL` | no |
| `delete_records` | `CRITICAL` | no |
| `drop_database_table` | `CRITICAL` | no |

## Gateway modes

| `mode` | Engine config for the request |
| --- | --- |
| `shield` (default) | the container's `ShieldConfig` unchanged |
| `guardrail` | `always_adjudicate=True` |
| `chaos` | `skip_classifier=True` |
