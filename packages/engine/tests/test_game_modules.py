"""The game package is a thin facade over its submodules (spec 0055)."""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

import shield_engine.game as game

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "packages" / "engine" / "src" / "shield_engine" / "game"
SUBMODULES = (
    "types",
    "detectors",
    "validation",
    "runner",
    "scoring",
    "levels",
    "agent",
    "custom",
    "model_signing",
)


@pytest.mark.spec("ENG-MOD-001")
def test_package_init_only_re_exports() -> None:
    source = (PACKAGE / "__init__.py").read_text()
    assert len(source.splitlines()) <= 150
    tree = ast.parse(source)
    defined = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]
    assert defined == []

    imported_from = {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 1
    }
    for name in SUBMODULES:
        assert (PACKAGE / f"{name}.py").exists(), name
        assert name in imported_from, name

    for name in game.__all__:
        assert hasattr(game, name), name


@pytest.mark.spec("ENG-MOD-002")
def test_every_import_from_the_package_resolves() -> None:
    pattern = re.compile(r"from shield_engine\.game import \(?([^)]*?)\)?\n(?!\s)", re.S)
    names: set[str] = set()
    for folder in ("packages/engine", "apps/api"):
        for path in (ROOT / folder).rglob("*.py"):
            if ".venv" in path.parts:
                continue
            for match in pattern.finditer(path.read_text()):
                for raw in match.group(1).replace("\n", " ").split(","):
                    name = raw.strip().split(" as ")[0].strip()
                    if name and name.isidentifier():
                        names.add(name)
    module = importlib.import_module("shield_engine.game")
    missing = sorted(name for name in names if not hasattr(module, name))
    assert missing == []

    # Each public function and class lives in a submodule; the package only re-exports it.
    homes = {f"shield_engine.game.{name}" for name in SUBMODULES}
    for name in game.__all__:
        value = getattr(game, name)
        home = getattr(value, "__module__", None)
        if callable(value) and home is not None and home.startswith("shield_engine"):
            assert home in homes or home.startswith("shield_engine.game."), (name, home)
            assert home != "shield_engine.game", name
