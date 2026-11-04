"""The simulated enterprise toolbox the demo assistant can call.

Everything here is fake data for demonstration. The risk labels are real
input to the engine's policy gate, so they are covered by tests
(API-TOOLS-001).
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from shield_engine import RiskLevel, ToolSpec


@dataclass(frozen=True, slots=True)
class DemoTool:
    name: str
    description: str
    risk: RiskLevel
    triggers: tuple[str, ...]
    """Lower-case phrases that make the demo router pick this tool."""

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.risk)


CATALOGUE: tuple[DemoTool, ...] = (
    DemoTool("search_documents", "Search the company handbook and internal policies",
             RiskLevel.LOW, ("policy", "handbook", "guideline", "leave")),
    DemoTool("search_quotations", "Search the product price list and quotations",
             RiskLevel.LOW, ("price", "quotation", "cost", "how much")),
    DemoTool("get_org_chart", "View the organisational structure and hierarchy",
             RiskLevel.MEDIUM, ("org chart", "hierarchy", "who reports", "manager of")),
    DemoTool("query_sales_database", "Query revenue, orders and product analytics",
             RiskLevel.HIGH, ("sales", "revenue", "orders")),
    DemoTool("get_employee_data", "Retrieve employee personal data (IC, phone, salary)",
             RiskLevel.HIGH, ("salary", "ic number", "employee data", "phone number")),
    DemoTool("send_email", "Send email on the user's behalf",
             RiskLevel.HIGH, ("send email", "email to")),
    DemoTool("export_data", "Export company data as a downloadable file",
             RiskLevel.HIGH, ("export",)),
    DemoTool("execute_sql", "Execute raw SQL (SELECT, INSERT, UPDATE, DELETE)",
             RiskLevel.CRITICAL, ("select ", "insert into", "update ", "execute sql", "raw sql")),
    DemoTool("delete_records", "Delete records from a table by condition",
             RiskLevel.CRITICAL, ("delete from", "delete records", "remove records")),
    DemoTool("drop_database_table", "PERMANENTLY drop a database table and all its data",
             RiskLevel.CRITICAL, ("drop table", "drop database")),
)  # fmt: skip


def route(prompt: str, allowed: list[str]) -> list[DemoTool]:
    """Pick the allowed tools whose trigger phrases appear in the prompt.

    A deliberately simple stand-in for LLM function calling: it keeps the
    demo deterministic and makes the policy gate's effect easy to see.
    """
    lowered = prompt.lower()
    return [
        tool
        for tool in CATALOGUE
        if tool.name in allowed and any(trigger in lowered for trigger in tool.triggers)
    ]


def _employee(_: str) -> dict[str, Any]:
    return {
        "name": "John Tan Wei Ming",
        "ic": "920515-10-5234",
        "phone": "+6012-3456789",
        "salary": "RM 12,000",
        "department": "Engineering",
    }


def _sales(_: str) -> dict[str, Any]:
    return {
        "total_revenue": "RM 1,248,500.00",
        "total_orders": 342,
        "top_products": ["Frankincense Oil: RM 345,000", "Lavender Essential Oil: RM 210,000"],
    }


def _org_chart(_: str) -> dict[str, Any]:
    return {
        "ceo": "Dato' Ahmad",
        "cto": "Sarah Lee",
        "departments": [
            {"name": "Engineering", "headcount": 12},
            {"name": "Sales", "headcount": 8},
        ],
    }


def _quotations(prompt: str) -> dict[str, Any]:
    return {"results": [{"source": "Price List", "content": "Standard enterprise rate: RM 150.00"}]}


def _documents(prompt: str) -> dict[str, Any]:
    return {"results": [{"source": "Handbook", "content": "See section 4: acceptable use policy."}]}


def _simulated(operation: str) -> Callable[[str], dict[str, Any]]:
    def run(prompt: str) -> dict[str, Any]:
        return {"success": True, "operation": operation, "note": "SIMULATION: nothing was changed."}

    return run


_EXECUTORS: dict[str, Callable[[str], dict[str, Any]]] = {
    "get_employee_data": _employee,
    "query_sales_database": _sales,
    "get_org_chart": _org_chart,
    "search_quotations": _quotations,
    "search_documents": _documents,
    "send_email": _simulated("SEND_EMAIL"),
    "export_data": _simulated("EXPORT"),
    "execute_sql": _simulated("EXECUTE_SQL"),
    "delete_records": _simulated("DELETE"),
    "drop_database_table": _simulated("DROP TABLE"),
}


async def execute(tool: DemoTool, prompt: str) -> dict[str, Any]:
    await asyncio.sleep(0)  # tools are async in real deployments
    return _EXECUTORS[tool.name](prompt)
