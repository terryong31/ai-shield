# 03 — System Architecture, Coding Standards & BYOD Strategy

## 1. Respecting Existing Architectural Rules (`AGENTS.md`)

To keep the repository clean, testable, and compliant with all existing architectural boundaries:

| Boundary | How the Game Refactor Respects It |
| :--- | :--- |
| **Pure Engine (`packages/engine`)** | The DAG graph evaluator, node executors, level wave definitions, and scoring math live inside `shield_engine` as pure Python 3.12 dataclasses and `Protocol`s—zero FastAPI or env imports. |
| **Thin Gateway (`apps/api`)** | Exposes `/api/v1/game/levels`, `/api/v1/game/run-wave` (SSE stream), and `/api/v1/game/leaderboard` (SQLite). |
| **Contract-First Web (`apps/web`)** | All new schemas in `shield_api/schemas.py` regenerate `contracts/shield-api.openapi.json` and `app/types/api.gen.ts` via `mise run contract`. |
| **Enforced SDD + TDD** | Every new capability is specified in `specs/0016-...` with testable acceptance criteria (`ENG-DAG-001`, `API-GAME-001`, `WEB-CANVAS-001`) before writing production code. |

---

## 2. Dynamic Workflow Graph Engine (`shield_engine/graph.py`)

Currently, `Pipeline` in `packages/engine/src/shield_engine/pipeline.py` runs a fixed sequence (`Classifier -> Moderation -> Debate -> ToolPolicy`).

We generalize this into a **Directed Acyclic Graph (DAG) Runner** (`WorkflowGraph`) that still reuses every existing detector:

```python
@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: Literal[
        "ingress",
        "regex_guard",
        "sanitizer",
        "ml_classifier",
        "moderation",
        "debate_judge",
        "agent",
        "tool_rbac",
        "canary_scanner",
        "oblivion",
    ]
    config: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class GraphEdge:
    id: str
    source: str
    source_handle: Literal["pass", "safe", "suspicious", "malicious", "tool_call"]
    target: str

@dataclass(frozen=True)
class WorkflowTopology:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
```

### Graph Execution Semantics
1. **Validation:** Rejects cycles, disconnected `ingress`, or missing `agent`/`oblivion` nodes before a wave starts.
2. **Packet Trace:** For each `WavePacket` in the level dataset, the runner traverses the player's `WorkflowTopology` starting at `ingress`.
3. **Hop Telemetry:** Every node visited emits a `NodeHopEvent(node_id, verdict, latency_ms, cost_usd, handle_taken)` so the frontend can animate the exact path and accumulate real or simulated metrics.

---

## 3. BYOD Dual-Execution Engine (Offline Zero-Key vs. Live LLM)

A critical requirement for open-source / BYOD adoption is that **clone + `mise run dev` must work out of the box in 5 seconds without an OpenAI API key**, while still allowing power users to plug in real models.

| Mode | How Nodes Run | Latency & Cost Calculation | Best For |
| :--- | :--- | :--- | :--- |
| **1. Deterministic Hybrid Mode (Default)** | - `Regex`, `Sanitizer`, `TF-IDF Classifier`, `Tool RBAC`, `Canary` run **100% live in Python** (`scikit-learn`).<br>- `DebateJudge` & `TargetAgent` use a deterministic **Semantic Replay Adapter** (backed by pre-evaluated embeddings + curated prosecutor/defender transcripts). | Uses realistic reference latency/cost model + actual local execution time. Fair, reproducible leaderboard scores! | Instant local play, classrooms, workshops, CI tests, fair scoreboards. |
| **2. Live BYOD LLM Mode** | All LLM nodes (`DebateJudge`, `Moderation`, `TargetAgent`) call the user's configured provider (`OpenAI`, `Anthropic`, `Gemini`, or local `Ollama` via OpenAI-compatible base URL). | Measures **actual wall-clock latency (`time.perf_counter`)** and **actual token usage (`prompt_tokens` + `completion_tokens`)**. | Testing custom prompts, live red-teaming, benchmarking local Ollama models. |

---

## 4. SQLite Leaderboard & Blueprint Persistence

We extend `SqliteAuditLog` (and Supabase migration mirror) with a `leaderboard_runs` table:
- `id` (UUID)
- `player_name` (TEXT)
- `level_id` (TEXT: `level_1`, `level_2`, `level_3`)
- `mode` (`deterministic` | `byod_live`)
- `score` (INTEGER)
- `medal` (`none` | `bronze` | `silver` | `gold`)
- `attacks_blocked_pct` (REAL)
- `false_positive_pct` (REAL)
- `avg_latency_ms` (REAL)
- `total_cost_usd` (REAL)
- `topology_json` (TEXT — stores the exact Vue Flow nodes & edges so players can replay or load top architectures!)
- `created_at` (TIMESTAMP)

