import pytest

from shield_engine import RiskLevel, ToolPolicy, ToolSpec, allowed_tools

CATALOGUE = [
    ToolSpec("search_documents", RiskLevel.LOW),
    ToolSpec("get_org_chart", RiskLevel.MEDIUM),
    ToolSpec("search_quotations", RiskLevel.LOW),
    ToolSpec("drop_database_table", RiskLevel.CRITICAL),
]


@pytest.mark.spec("ENG-POL-001")
def test_allow_all_keeps_every_tool_in_order() -> None:
    assert allowed_tools(ToolPolicy.ALLOW_ALL, CATALOGUE) == [
        "search_documents",
        "get_org_chart",
        "search_quotations",
        "drop_database_table",
    ]


@pytest.mark.spec("ENG-POL-002")
def test_restricted_keeps_only_low_risk_tools() -> None:
    assert allowed_tools(ToolPolicy.RESTRICTED, CATALOGUE) == [
        "search_documents",
        "search_quotations",
    ]


@pytest.mark.spec("ENG-POL-003")
def test_shutdown_allows_nothing() -> None:
    assert allowed_tools(ToolPolicy.SHUTDOWN, CATALOGUE) == []
