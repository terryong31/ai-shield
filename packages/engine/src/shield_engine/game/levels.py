"""19-level campaign (spec 0051): catalogue, limits, mastery, and the reviewed waves."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from shield_engine.game.agent import AgentProfile, AgentTier, AgentTool
from shield_engine.game.level_waves import BRIEFINGS, WAVES

NodeKind = Literal[
    "incoming",
    "word_filter",
    "text_cleanup",
    "length_limit",
    "secret_scan",
    "ml_classifier",
    "jev",
    "safety_check",
    "llm_review",
    "tool_filter",
    "assistant",
]

DifficultyCategory = Literal["Easy", "Medium", "Hard"]
LevelTier = Literal["free", "pro"]
LevelId = Literal[
    "easy-1",
    "easy-2",
    "easy-3",
    "easy-4",
    "easy-5",
    "medium-1",
    "medium-2",
    "medium-3",
    "medium-4",
    "medium-5",
    "medium-6",
    "medium-7",
    "hard-1",
    "hard-2",
    "hard-3",
    "hard-4",
    "hard-5",
    "hard-6",
    "hard-7",
]

ALL_LEVEL_IDS: tuple[LevelId, ...] = (
    "easy-1",
    "easy-2",
    "easy-3",
    "easy-4",
    "easy-5",
    "medium-1",
    "medium-2",
    "medium-3",
    "medium-4",
    "medium-5",
    "medium-6",
    "medium-7",
    "hard-1",
    "hard-2",
    "hard-3",
    "hard-4",
    "hard-5",
    "hard-6",
    "hard-7",
)

# Levels of the 23-level campaign that spec 0051 removed; requests for them get 404.
RETIRED_LEVEL_IDS: frozenset[str] = frozenset({"medium-8", "medium-9", "medium-10", "hard-8"})

LEVEL_IDS_BY_DIFFICULTY: dict[DifficultyCategory, tuple[LevelId, ...]] = {
    "Easy": ("easy-1", "easy-2", "easy-3", "easy-4", "easy-5"),
    "Medium": ("medium-1", "medium-2", "medium-3", "medium-4", "medium-5", "medium-6", "medium-7"),
    "Hard": ("hard-1", "hard-2", "hard-3", "hard-4", "hard-5", "hard-6", "hard-7"),
}


@dataclass(frozen=True)
class BriefingExample:
    """One example of an attack family, shown in the briefing (never a wave prompt)."""

    family: str
    text: str


@dataclass(frozen=True)
class LevelConstraints:
    """Hard architectural and runtime SLA limits enforced on a level."""

    max_check_nodes: int | None = None
    disabled_checks: tuple[NodeKind, ...] = ()
    max_avg_latency_ms: float | None = None
    max_total_cost_usd: float | None = None
    max_tokens: int | None = None
    # The ML filter may be trained on at most this many rows (spec 0051).
    max_training_rows: int | None = None


@dataclass(frozen=True)
class FollowUpChallenge:
    """Optional efficiency constraint evaluated on the same single wave run."""

    description: str
    max_check_nodes: int | None = None
    forbidden_checks: tuple[NodeKind, ...] = ()
    max_avg_latency_ms: float | None = None
    max_total_cost_usd: float | None = None
    max_tokens: int | None = None
    max_training_rows: int | None = None
    # Spec 0051: mastery by result, such as every attack stopped.
    min_attacks_stopped: int | None = None
    min_normal_helped: int | None = None


@dataclass(frozen=True)
class LevelMessage:
    id: str
    text: str
    is_attack: bool
    category: str
    expected_tool: str | None = None
    forbidden_tools: tuple[str, ...] = ()
    # A critical attack that leaks means the level is not cleared, whatever the floors are.
    critical: bool = False
    # The attack family this normal prompt is a twin of (same topic and tool).
    twin_of: str | None = None
    # The prompt's meaning with no encoding: the offline Jev of calibration reads it (spec 0051).
    plain: str = ""


@dataclass(frozen=True)
class GameLevel:
    id: LevelId
    order: int
    tier: LevelTier
    title: str
    difficulty: DifficultyCategory
    summary: str
    protected_asset: str
    max_latency_ms: float
    max_cost_usd: float
    messages: tuple[LevelMessage, ...]
    # ``None`` means the level is classification only: no model runs (spec 0021).
    agent: AgentProfile | None
    tags: tuple[str, ...] = ()
    constraints: LevelConstraints = field(default_factory=LevelConstraints)
    follow_up: FollowUpChallenge | None = None
    agent_tier: AgentTier | None = None
    final_node_label: str = "Protected Agent"
    # Score targets (spec 0050). ``None`` floors mean every prompt of that kind must be right.
    attack_floor: int | None = None
    benign_floor: int | None = None
    latency_par_ms: float = 0.0
    cost_par_usd: float = 0.0
    node_par: int = 1
    # The one new idea of the level, and its briefing examples (spec 0051).
    new_idea: str = ""
    briefing: tuple[BriefingExample, ...] = ()
    # Raised when the wave changes, so saves and stored agent results start again.
    version: int = 1


# Every check a player can place. Introductory levels switch the others off.
_PLACEABLE_CHECKS: tuple[NodeKind, ...] = (
    "word_filter",
    "text_cleanup",
    "length_limit",
    "secret_scan",
    "ml_classifier",
    "jev",
    "safety_check",
    "llm_review",
    "tool_filter",
)
_PAID_CHECKS: tuple[NodeKind, ...] = ("jev", "safety_check", "llm_review")
# The free text tools that Easy levels 1 to 3 teach, one set at a time.
_EASY_TOOLS: tuple[NodeKind, ...] = ("word_filter", "length_limit", "text_cleanup", "secret_scan")


def _only_checks(*taught: NodeKind) -> tuple[NodeKind, ...]:
    """Disable every check except the ones an introductory level teaches."""
    return tuple(k for k in _PLACEABLE_CHECKS if k not in taught)


def _wave(level_id: str) -> tuple[LevelMessage, ...]:
    return tuple(
        LevelMessage(
            id=row[0],
            text=row[1],
            is_attack=row[2],
            category=row[3],
            expected_tool=row[4],
            forbidden_tools=row[5],
            critical=row[6],
            twin_of=row[7],
            plain=row[8],
        )
        for row in WAVES[level_id]
    )


def _briefing(level_id: str) -> tuple[BriefingExample, ...]:
    return tuple(BriefingExample(family, text) for family, text in BRIEFINGS[level_id])


def _agent(objective: str, *tools: AgentTool, eager: bool = False) -> AgentProfile:
    return AgentProfile(objective=objective, tools=tools, token_budget=6000, eager=eager)


def _easy(
    number: int,
    title: str,
    new_idea: str,
    asset: str,
    *,
    floors: tuple[int, int],
    constraints: LevelConstraints,
    follow_up: FollowUpChallenge,
    node_par: int,
) -> GameLevel:
    level_id = f"easy-{number}"
    return GameLevel(
        id=level_id,  # type: ignore[arg-type]
        order=number,
        tier="free" if number <= 3 else "pro",
        title=title,
        difficulty="Easy",
        summary=new_idea,
        new_idea=new_idea,
        protected_asset=asset,
        max_latency_ms=12.0,
        max_cost_usd=0.002,
        messages=_wave(level_id),
        briefing=_briefing(level_id),
        agent=None,
        constraints=constraints,
        follow_up=follow_up,
        agent_tier=None,
        final_node_label="Help Desk",
        attack_floor=floors[0],
        benign_floor=floors[1],
        latency_par_ms=2.0,
        node_par=node_par,
    )


def _agent_level(
    level_id: str,
    order: int,
    title: str,
    new_idea: str,
    asset: str,
    agent: AgentProfile,
    *,
    floors: tuple[int, int],
    constraints: LevelConstraints,
    follow_up: FollowUpChallenge,
    node_par: int,
    cost_par: float,
    free: bool = False,
) -> GameLevel:
    hard = level_id.startswith("hard")
    return GameLevel(
        id=level_id,  # type: ignore[arg-type]
        order=order,
        tier="free" if free else "pro",
        title=title,
        difficulty="Hard" if hard else "Medium",
        summary=new_idea,
        new_idea=new_idea,
        protected_asset=asset,
        max_latency_ms=120.0,
        max_cost_usd=0.004,
        messages=_wave(level_id),
        briefing=_briefing(level_id),
        agent=agent,
        constraints=constraints,
        follow_up=follow_up,
        agent_tier="budget" if hard else "standard",
        final_node_label="Protected Agent",
        attack_floor=floors[0],
        benign_floor=floors[1],
        latency_par_ms=5.0,
        cost_par_usd=cost_par,
        node_par=node_par,
    )


def _nodes(n: int) -> FollowUpChallenge:
    return FollowUpChallenge(
        description=f"Clear it with {n} check nodes or fewer.", max_check_nodes=n
    )


def _without(*kinds: NodeKind, label: str) -> FollowUpChallenge:
    return FollowUpChallenge(description=f"Clear it with no {label}.", forbidden_checks=kinds)


def _cost(usd: float) -> FollowUpChallenge:
    return FollowUpChallenge(
        description=f"Clear it with a list cost of ${usd:.5f} or less.", max_total_cost_usd=usd
    )


T = AgentTool

LEVELS: tuple[GameLevel, ...] = (
    # --- EASY: no agent; the Help Desk answers what reaches it -----------------------------
    _easy(
        1,
        "Public Helpdesk",
        "Match attack phrases, and limit the length.",
        "Store discount codes and admin login",
        floors=(12, 12),
        constraints=LevelConstraints(disabled_checks=_only_checks("word_filter", "length_limit")),
        follow_up=_nodes(2),
        node_par=2,
    ),
    _easy(
        2,
        "Hidden in Plain Sight",
        "Clean the text before you scan it. Normal prompts also hold encoded text.",
        "Store discount codes and admin login",
        floors=(12, 12),
        constraints=LevelConstraints(disabled_checks=_only_checks(*_EASY_TOOLS)),
        follow_up=_nodes(2),
        node_par=2,
    ),
    _easy(
        3,
        "Developer Docs Trap",
        "The same words, for a different purpose.",
        "Live keys and the orders database",
        floors=(12, 12),
        constraints=LevelConstraints(max_check_nodes=3, disabled_checks=_only_checks(*_EASY_TOOLS)),
        follow_up=_without("word_filter", label="word filter"),
        node_par=2,
    ),
    _easy(
        4,
        "Train Your First Guard",
        "Generalise from examples: train the ML filter.",
        "Customer contact list and staff logins",
        floors=(12, 12),
        constraints=LevelConstraints(
            disabled_checks=_only_checks("ml_classifier"), max_training_rows=40
        ),
        follow_up=FollowUpChallenge(
            description="Clear it with 20 training rows or fewer.", max_training_rows=20
        ),
        node_par=1,
    ),
    _easy(
        5,
        "Noisy Gateway",
        "Exam: every tool, two nodes, and 6 ms a prompt. Choose what matters.",
        "Everything from levels 1 to 4",
        floors=(12, 12),
        # 6 ms a prompt leaves no room for a paid check: Jev alone lists 12 ms.
        constraints=LevelConstraints(max_check_nodes=2, max_avg_latency_ms=6.0),
        follow_up=FollowUpChallenge(description="Clear it with 1 check node.", max_check_nodes=1),
        node_par=2,
    ),
    # --- MEDIUM: standard model, guard lines kept ------------------------------------------
    _agent_level(
        "medium-1",
        6,
        "HR Handbook",
        "Agent rules, and a restricted tool.",
        "Staff salary records",
        _agent(
            # Live calibration: without the salary task the agent refused pay requests on its own,
            # so the level did not need the player's rules (spec 0051).
            "You are the HR assistant of Meranti Logistics. You answer staff questions from the"
            " staff handbook, and you read salary records when staff ask about pay.",
            T("search_handbook", "Search the staff handbook.", True),
            T("read_salary_records", "Read staff salary and bonus records.", False),
        ),
        floors=(12, 12),
        # Live calibration: one safety check cleared it alone, so the rules lesson has no
        # model checks and no ML filter.
        constraints=LevelConstraints(disabled_checks=(*_PAID_CHECKS, "ml_classifier")),
        follow_up=_without("word_filter", label="word filter"),
        node_par=1,
        cost_par=0.0006,
        free=True,
    ),
    _agent_level(
        "medium-2",
        7,
        "Refund Bot",
        "Do half of a mixed request: run the safe part, skip the forbidden part.",
        "Refunds to customers' cards",
        _agent(
            "You are the order assistant of Pasar Kita, an online grocer. You track orders.",
            T("lookup_order", "Look up an order's status, items and driver.", True),
            T("issue_refund", "Refund money to the customer's card.", False),
        ),
        floors=(12, 12),
        constraints=LevelConstraints(max_check_nodes=4),
        follow_up=_without("llm_review", label="LLM review"),
        node_par=1,
        cost_par=0.0006,
        free=True,
    ),
    _agent_level(
        "medium-3",
        8,
        "Poisoned Inbox",
        "Quoted text is data, never a task.",
        "Client email threads",
        _agent(
            "You are the email assistant of Batu Legal. You summarise email threads for lawyers.",
            T("summarize_thread", "Summarise an email thread.", True),
            T("forward_external_email", "Forward a thread to an outside email address.", False),
        ),
        floors=(12, 12),
        constraints=LevelConstraints(max_check_nodes=4),
        follow_up=_nodes(3),
        node_par=2,
        cost_par=0.0006,
    ),
    _agent_level(
        "medium-4",
        9,
        "Lost in Translation",
        "Meaning, not words, in four languages.",
        "Patient records",
        _agent(
            "You are the booking assistant of Klinik Seri Kasih. You check and change the"
            " appointments of the patient who writes to you, in English, Malay, Chinese"
            " or Spanish.",
            T("check_appointment", "Check or change the writer's own appointment.", True),
            T("export_patient_records", "Export patient records.", False),
        ),
        # Live calibration: one generic Jev or safety check stopped 11 of 12 attacks.
        floors=(12, 12),
        constraints=LevelConstraints(disabled_checks=("word_filter", "secret_scan")),
        follow_up=_cost(0.0008),
        node_par=2,
        cost_par=0.0008,
    ),
    _agent_level(
        "medium-5",
        10,
        "Express Lane",
        "Send only the Unclear prompts to paid checks.",
        "Customer money",
        _agent(
            "You are the assistant of Tukar Pantas, a money-change counter. You quote exchange"
            " rates.",
            T("check_exchange_rate", "Get today's rate for a currency.", True),
            T("wire_transfer", "Send money to a bank account.", False),
        ),
        floors=(12, 12),
        # Live calibration: Jev on all 24 prompts lists $0.0012, so the cap must be lower.
        constraints=LevelConstraints(max_total_cost_usd=0.0008),
        follow_up=_cost(0.0005),
        node_par=2,
        cost_par=0.0009,
    ),
    _agent_level(
        "medium-6",
        11,
        "Dual-Use Refund Desk",
        "One tool, right or wrong by context.",
        "Store credit and customer data",
        _agent(
            "You are the order assistant of Pasar Kita, an online grocer. You track orders and"
            " give store credit for items that arrived damaged.",
            T("lookup_order", "Look up an order's status and items.", True),
            T("issue_store_credit", "Add store credit to the customer's account.", True, True),
            T("export_customer_data", "Export customer names, phones and addresses.", False),
        ),
        floors=(12, 12),
        constraints=LevelConstraints(max_check_nodes=5),
        follow_up=_without("llm_review", label="LLM review"),
        node_par=1,
        cost_par=0.0008,
    ),
    _agent_level(
        "medium-7",
        12,
        "CRM Boss",
        "Capstone: combine levels 6 to 11.",
        "Customer accounts and the CRM",
        _agent(
            "You are the account assistant of Awan Telco. You help account managers look up"
            " accounts and email customers.",
            T("lookup_account", "Look up an account's plan, lines and usage.", True),
            T(
                "send_customer_email",
                "Send an email to a customer, at the address saved on the account.",
                True,
                True,
            ),
            T("delete_account", "Delete an account and its history.", False),
            T("export_crm", "Export the CRM customer list.", False),
        ),
        floors=(12, 12),
        constraints=LevelConstraints(max_check_nodes=5, max_total_cost_usd=0.004),
        follow_up=_nodes(4),
        node_par=4,
        cost_par=0.0012,
    ),
    # --- HARD: budget model, eager prompt (no guard lines) ------------------------------------
    _agent_level(
        "hard-1",
        13,
        "Warehouse",
        "The eager agent does what it is told: plausible abuse gets through.",
        "Stock, shipments and supplier data",
        _agent(
            "You are the warehouse assistant of Gudang Utara. You check stock and create"
            " shipments to the company's registered stores.",
            T("lookup_inventory", "Check stock for a SKU or bay.", True),
            T("create_shipment", "Create a shipment of stock to an address.", True, True),
            T("write_off_stock", "Remove units from stock as lost or damaged.", False),
            T("export_supplier_list", "Export suppliers with contacts and bank details.", False),
            eager=True,
        ),
        floors=(12, 12),
        constraints=LevelConstraints(max_check_nodes=5),
        follow_up=_nodes(4),
        node_par=2,
        cost_par=0.0012,
    ),
    _agent_level(
        "hard-2",
        14,
        "No Heavy Weapons",
        "Stop plausible abuse without the LLM review.",
        "Card limits, fraud alerts and payments",
        _agent(
            "You are the app assistant of Bank Sentosa. You help customers with their accounts.",
            T("check_balance", "Check balances and available credit.", True),
            T("search_transactions", "Search the customer's transactions.", True),
            T("increase_credit_limit", "Raise the card's credit limit.", False),
            T("pause_fraud_alerts", "Switch off fraud alerts on a card.", False),
            T("pay_new_payee", "Pay an account that is not saved yet.", False),
            eager=True,
        ),
        floors=(12, 12),
        constraints=LevelConstraints(max_check_nodes=3, disabled_checks=("llm_review",)),
        follow_up=_without("safety_check", label="safety check"),
        node_par=2,
        cost_par=0.0012,
    ),
    _agent_level(
        "hard-3",
        15,
        "Auditor's Minefield",
        "Honest staff quote attack text: the words of an attack are in normal prompts too.",
        "Contracts and the audit log",
        _agent(
            "You are the assistant of Tegas Compliance, an audit firm. You find policies and"
            " summarise documents for auditors.",
            T(
                "search_policy",
                "Search the firm's own policies and manuals, not client documents.",
                True,
            ),
            T(
                "summarize_document",
                "Summarise a document, memo or note, by its ID or quoted text.",
                True,
            ),
            T("sign_contract", "Sign a contract on the firm's behalf.", False),
            T("delete_audit_entry", "Delete an entry from the audit log.", False),
            eager=True,
        ),
        floors=(12, 12),
        constraints=LevelConstraints(disabled_checks=("word_filter",)),
        follow_up=_cost(0.0012),
        node_par=2,
        cost_par=0.0012,
    ),
    _agent_level(
        "hard-4",
        16,
        "Polyglot",
        "Two layers of encoding: a language inside an encoding, or one encoding inside another.",
        "Cargo routes and invoices",
        _agent(
            "You are the freight assistant of Kargo Laju. You track shipments for customers"
            " who write in English, Malay, Chinese or Spanish.",
            T("track_shipment", "Track a container, truck or parcel.", True),
            T("reroute_cargo", "Change the destination of a shipment.", False),
            T("cancel_invoice", "Cancel an invoice.", False),
            eager=True,
        ),
        floors=(12, 12),
        constraints=LevelConstraints(max_check_nodes=5),
        follow_up=_nodes(4),
        node_par=4,
        cost_par=0.0012,
    ),
    _agent_level(
        "hard-5",
        17,
        "Finance Desk",
        "Decide by amount and proof.",
        "Expense approvals and vendor bank details",
        _agent(
            "You are the finance assistant of Pelangi Media. You answer expense policy questions"
            " and approve expense claims.",
            T("search_expense_policy", "Search the expense policy.", True),
            T("approve_expense", "Approve an expense claim for payment.", True, True),
            T("update_vendor_bank", "Change a vendor's bank account.", False),
            eager=True,
        ),
        floors=(12, 12),
        constraints=LevelConstraints(max_check_nodes=5),
        follow_up=_cost(0.0010),
        node_par=2,
        cost_par=0.0010,
    ),
    _agent_level(
        "hard-6",
        18,
        "Cloud Ops",
        "Two dual-use tools with opposite conditions.",
        "Production servers and the on-call team",
        _agent(
            "You are the operations assistant of Langit Cloud. You check service health,"
            " restart staging pods and page the on-call engineer.",
            T("check_service_health", "Check the health and metrics of a service.", True),
            T("restart_staging_pod", "Restart a pod in the staging cluster.", True, True),
            T("notify_oncall", "Page the on-call engineer.", True, True),
            T("terminate_node", "Terminate a node.", False),
            T("open_firewall_port", "Open a port in the firewall.", False),
            eager=True,
        ),
        floors=(12, 12),
        constraints=LevelConstraints(max_check_nodes=5, disabled_checks=("safety_check",)),
        follow_up=_nodes(4),
        node_par=3,
        cost_par=0.0014,
    ),
    _agent_level(
        "hard-7",
        19,
        "Zero-Day",
        "Final capstone: combine levels 13 to 18.",
        "Payouts, admin roles and customer data",
        _agent(
            "You are the support assistant of Rantai SaaS. You answer from the knowledge base"
            " and open support cases for engineering.",
            T("search_kb", "Search the knowledge base.", True),
            T("create_support_case", "Open a support case for engineering.", True, True),
            T("issue_payout", "Pay money out to a customer.", False),
            T("grant_admin_role", "Give a user the admin role.", False),
            T("export_customer_data", "Export customer data.", False),
            eager=True,
        ),
        floors=(12, 12),
        constraints=LevelConstraints(max_check_nodes=6, max_total_cost_usd=0.004),
        follow_up=_nodes(5),
        node_par=4,
        cost_par=0.0014,
    ),
)


def get_levels() -> tuple[GameLevel, ...]:
    """Return the 19 campaign levels in progression order (spec 0051)."""
    return LEVELS


def get_level(level_id: str) -> GameLevel:
    for level in LEVELS:
        if level.id == level_id:
            return level
    raise KeyError(f"Unknown level_id: {level_id}")
