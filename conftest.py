"""Repo-wide pytest plugin: run tests by acceptance-criterion ID (spec 0010).

    pytest --spec-ids=ENG-PIPE-001,API-CHAT-002 --spec-report=out.json

Only tests marked ``@pytest.mark.spec("<ID>")`` for one of the IDs run. The
JSON report records each test's outcome, plus collection errors of files that
mention the IDs, which ``scripts/sdd.py`` uses to judge RED and GREEN.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest


@dataclass
class _Session:
    wanted: set[str] = field(default_factory=set)
    items: dict[str, list[str]] = field(default_factory=dict)
    results: dict[str, dict[str, str]] = field(default_factory=dict)
    collect_errors: list[dict[str, str]] = field(default_factory=list)


_session = _Session()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("spec")
    group.addoption("--spec-ids", default="", help="comma-separated criterion IDs to run")
    group.addoption("--spec-report", default="", help="write per-test outcomes as JSON here")


def pytest_configure(config: pytest.Config) -> None:
    _session.wanted = {i for i in str(config.getoption("--spec-ids")).split(",") if i}


def pytest_collectreport(report: pytest.CollectReport) -> None:
    if report.failed and report.fspath:
        _session.collect_errors.append(
            {"path": str(report.fspath), "message": str(report.longrepr)}
        )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not _session.wanted:
        return
    selected, deselected = [], []
    for item in items:
        ids = sorted(
            {str(m.args[0]) for m in item.iter_markers("spec") if m.args} & _session.wanted
        )
        if ids:
            _session.items[item.nodeid] = ids
            selected.append(item)
        else:
            deselected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    previous = _session.results.get(report.nodeid)
    if previous and previous["outcome"] != "passed":
        return  # keep the first problem (a setup error outranks the call phase)
    if report.when == "call":
        outcome = report.outcome
    elif report.failed:
        outcome = "error"
    elif report.skipped:
        outcome = "skipped"
    else:
        return
    _session.results[report.nodeid] = {
        "outcome": outcome,
        "message": str(report.longrepr)[-2000:] if report.failed else "",
    }


def pytest_sessionfinish(session: pytest.Session) -> None:
    target = str(session.config.getoption("--spec-report"))
    if not target:
        return
    report: dict[str, Any] = {
        "items": [
            {"nodeid": nodeid, "ids": ids, **_session.results.get(nodeid, {"outcome": "error"})}
            for nodeid, ids in _session.items.items()
        ],
        "collect_errors": [],
    }
    for error in _session.collect_errors:
        try:
            text = Path(error["path"]).read_text(encoding="utf-8")
        except OSError:
            continue
        ids = sorted(i for i in _session.wanted if i in text)
        if ids:
            report["collect_errors"].append({**error, "ids": ids})
    Path(target).write_text(json.dumps(report, indent=2), encoding="utf-8")
