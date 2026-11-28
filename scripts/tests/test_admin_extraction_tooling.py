"""Spec 0059: multi-app SDD and CI monorepo tooling tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import sdd

ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.spec("DEV-SDD-001")
def test_sdd_guards_and_discovers_all_apps_js_workspaces(repo) -> None:
    root = repo()
    # Production code in apps/admin and apps/landing must be guarded during spec phase.
    sdd.Workflow(root).start("0042")

    allowed_admin_prod, _ = sdd.guard_edit(
        root, "Edit", {"file_path": str(root / "apps/admin/app/pages/index.vue")}
    )
    allowed_landing_prod, _ = sdd.guard_edit(
        root, "Edit", {"file_path": str(root / "apps/landing/app/pages/index.vue")}
    )
    allowed_admin_test, _ = sdd.guard_edit(
        root, "Edit", {"file_path": str(root / "apps/admin/test/admin.test.ts")}
    )
    assert not allowed_admin_prod
    assert not allowed_landing_prod
    assert allowed_admin_test

    # _web_app_dirs must discover any apps/* directory with package.json + test/.
    (root / "apps" / "admin" / "test").mkdir(parents=True)
    (root / "apps" / "admin" / "package.json").write_text("{}", encoding="utf-8")
    dirs = sdd._web_app_dirs(root)
    assert root / "apps" / "admin" in dirs


@pytest.mark.spec("DEV-CI-001")
def test_monorepo_config_includes_apps_admin() -> None:
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert "apps/*" in pkg["workspaces"]

    affected = (ROOT / "scripts" / "affected.sh").read_text(encoding="utf-8")
    assert "deploy-admin)" in affected
    assert "ci-admin)" in affected

    mise = (ROOT / "mise.toml").read_text(encoding="utf-8")
    assert '[tasks."test:admin"]' in mise
    assert '[tasks."lint:admin"]' in mise
    assert '[tasks."typecheck:admin"]' in mise
    assert '[tasks."build:admin"]' in mise
    assert "apps/admin/app/types/api.gen.ts" in mise

    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "test:admin" in ci
    assert "lint:admin" in ci
    assert "typecheck:admin" in ci
