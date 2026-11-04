"""Spec 0010: the enforced SDD + TDD lifecycle and its agent guards."""

from pathlib import Path

import pytest
import sdd
from sdd import SddError, TestOutcome, TestRun, Workflow

PROD = "packages/engine/src/shield_engine/pipeline.py"
TEST = "packages/engine/tests/test_pipeline.py"


def outcomes(**by_id: str) -> TestRun:
    """outcomes(ENG_EX_001="failed,passed") -> TestRun keyed by real IDs."""
    return TestRun(
        by_id={
            key.replace("_", "-"): [
                TestOutcome(name=f"{key}_{i}", status=status)
                for i, status in enumerate(value.split(","))
                if status
            ]
            for key, value in by_id.items()
        }
    )


class FakeRunner:
    def __init__(self, *runs: TestRun) -> None:
        self.runs = list(runs)
        self.calls: list[list[str]] = []

    def __call__(self, root: Path, ids: list[str]) -> TestRun:
        self.calls.append(ids)
        return self.runs.pop(0)


def workflow(root: Path, *runs: TestRun, gate: bool = True) -> Workflow:
    return Workflow(
        root, runner=FakeRunner(*runs), gate=lambda root: gate, commit=lambda: "abc1234"
    )


def edit(root: Path, path: str, **tool_input) -> tuple[bool, str]:
    return sdd.guard_edit(root, "Edit", {"file_path": str(root / path), **tool_input})


# --- start ---------------------------------------------------------------------


@pytest.mark.spec("DEV-SDD-001")
@pytest.mark.parametrize("status", ["Draft", "Superseded by 0043"])
def test_start_refuses_specs_that_are_not_accepted(repo, status: str) -> None:
    with pytest.raises(SddError, match="Accepted"):
        workflow(repo(status)).start("0042")


@pytest.mark.spec("DEV-SDD-001")
def test_start_refuses_unknown_specs_and_ids(repo) -> None:
    root = repo()
    with pytest.raises(SddError, match="0099"):
        workflow(root).start("0099")
    with pytest.raises(SddError, match="ENG-EX-999"):
        workflow(root).start("0042", ["ENG-EX-999"])


@pytest.mark.spec("DEV-SDD-001")
def test_start_targets_all_criteria_by_default_or_a_subset(repo) -> None:
    root = repo()
    workflow(root).start("0042")
    assert sdd.load_state(root)["ids"] == ["ENG-EX-001", "ENG-EX-002"]
    assert sdd.load_state(root)["phase"] == "spec"

    workflow(root).start("0042", ["ENG-EX-002"])
    assert sdd.load_state(root)["ids"] == ["ENG-EX-002"]


# --- red -------------------------------------------------------------------------


@pytest.mark.spec("DEV-SDD-002")
def test_red_refuses_when_a_criterion_has_no_test(repo) -> None:
    root = repo()
    flow = workflow(root, outcomes(ENG_EX_001="failed", ENG_EX_002=""))
    flow.start("0042")

    with pytest.raises(SddError, match="ENG-EX-002"):
        flow.red()
    assert sdd.load_state(root)["phase"] == "spec"


@pytest.mark.spec("DEV-SDD-003")
def test_red_advances_when_every_criterion_has_a_failing_test(repo) -> None:
    root = repo()
    flow = workflow(root, outcomes(ENG_EX_001="failed,passed", ENG_EX_002="failed"))
    flow.start("0042")

    flow.red()

    state = sdd.load_state(root)
    assert state["phase"] == "red"
    assert state["red"]["failed"] == 2


@pytest.mark.spec("DEV-SDD-003")
def test_red_refuses_when_a_criterion_already_passes(repo) -> None:
    flow = workflow(repo(), outcomes(ENG_EX_001="failed", ENG_EX_002="passed,passed"))
    flow.start("0042")

    with pytest.raises(SddError, match=r"ENG-EX-002.*already pass"):
        flow.red()


@pytest.mark.spec("DEV-SDD-003")
def test_red_refuses_illegitimate_errors(repo) -> None:
    flow = workflow(repo(), outcomes(ENG_EX_001="error", ENG_EX_002="failed"))
    flow.start("0042")

    with pytest.raises(SddError, match="ENG-EX-001"):
        flow.red()


@pytest.mark.spec("DEV-SDD-003")
@pytest.mark.parametrize(
    ("message", "legitimate"),
    [
        ("ImportError: cannot import name 'SqliteAuditLog' from 'shield_api.services.audit'", True),
        ("ModuleNotFoundError: No module named 'shield_engine.detectors.heuristics'", True),
        ("AttributeError: module 'shield_engine' has no attribute 'Foo'", True),
        ("SyntaxError: invalid syntax", False),
        ("ModuleNotFoundError: No module named 'hypothesis'", False),
        ("NameError: name 'pytset' is not defined", False),
    ],
)
def test_only_missing_production_symbols_count_as_legitimate_collection_errors(
    message: str, legitimate: bool
) -> None:
    assert sdd.is_legitimate_collection_error(message) is legitimate


# --- green / verify / done ------------------------------------------------------


def to_red(root: Path, *later: TestRun, gate: bool = True) -> Workflow:
    flow = workflow(root, outcomes(ENG_EX_001="failed", ENG_EX_002="failed"), *later, gate=gate)
    flow.start("0042")
    flow.red()
    return flow


@pytest.mark.spec("DEV-SDD-004")
def test_green_requires_every_test_to_pass(repo) -> None:
    root = repo()
    flow = to_red(
        root,
        outcomes(ENG_EX_001="passed", ENG_EX_002="passed,failed"),
        outcomes(ENG_EX_001="passed", ENG_EX_002="passed,passed"),
    )

    with pytest.raises(SddError, match="ENG-EX-002"):
        flow.green()
    assert sdd.load_state(root)["phase"] == "red"

    flow.green()
    assert sdd.load_state(root)["phase"] == "green"
    assert sdd.load_state(root)["green"]["passed"] == 3


@pytest.mark.spec("DEV-SDD-004")
def test_green_cannot_skip_red(repo) -> None:
    flow = workflow(repo())
    flow.start("0042")

    with pytest.raises(SddError, match="sdd:red"):
        flow.green()


@pytest.mark.spec("DEV-SDD-005")
def test_verify_requires_green_and_a_passing_gate(repo) -> None:
    root = repo()
    flow = to_red(root, outcomes(ENG_EX_001="passed", ENG_EX_002="passed"), gate=False)

    with pytest.raises(SddError, match="sdd:green"):
        flow.verify()
    flow.green()
    with pytest.raises(SddError, match="mise run check"):
        flow.verify()
    assert sdd.load_state(root)["phase"] == "green"

    flow.gate = lambda root: True
    flow.verify()
    assert sdd.load_state(root)["phase"] == "verified"


@pytest.mark.spec("DEV-SDD-006")
def test_done_requires_verified(repo) -> None:
    flow = to_red(repo())

    with pytest.raises(SddError, match="sdd:verify"):
        flow.done()


@pytest.mark.spec("DEV-SDD-006")
def test_done_updates_the_spec_and_tasks_and_clears_state(repo) -> None:
    root = repo()
    flow = to_red(root, outcomes(ENG_EX_001="passed", ENG_EX_002="passed"))
    flow.green()
    flow.verify()

    flow.done()

    spec = (root / "specs/0042-example/spec.md").read_text()
    assert "- **Status:** Implemented" in spec
    assert "## Verification" in spec
    assert "commit abc1234" in spec
    assert "ENG-EX-001, ENG-EX-002" in spec
    assert "Red: 2 failing" in spec
    assert "Green: 2 passing" in spec
    assert "`mise run check` passed" in spec
    tasks = (root / "specs/0042-example/tasks.md").read_text()
    assert "- [x] **ENG-EX-001**" in tasks
    assert "- [x] **ENG-EX-002**" in tasks
    assert "- [ ] Update docs" in tasks
    assert sdd.load_state(root) is None


@pytest.mark.spec("DEV-SDD-006")
def test_a_second_cycle_appends_to_the_existing_verification_section(repo) -> None:
    root = repo()
    for _ in range(2):
        flow = to_red(root, outcomes(ENG_EX_001="passed", ENG_EX_002="passed"))
        flow.green()
        flow.verify()
        flow.done()

    spec = (root / "specs/0042-example/spec.md").read_text()
    assert spec.count("## Verification") == 1
    assert spec.count("commit abc1234") == 2


# --- guard: edits ----------------------------------------------------------------


@pytest.mark.spec("DEV-SDD-007")
@pytest.mark.parametrize(
    "path",
    [
        PROD,
        "apps/api/src/shield_api/main.py",
        "apps/web/app/components/chat/ChatInterface.vue",
        "supabase/migrations/20260101000000_x.sql",
    ],
)
def test_production_edits_are_denied_before_red(repo, path: str) -> None:
    root = repo()
    allowed, reason = edit(root, path)
    assert not allowed
    assert "sdd:start" in reason

    workflow(root).start("0042")
    allowed, reason = edit(root, path)
    assert not allowed
    assert "sdd:red" in reason


@pytest.mark.spec("DEV-SDD-007")
def test_production_edits_are_allowed_after_red_and_reopen_verified_cycles(repo) -> None:
    root = repo()
    flow = to_red(root, outcomes(ENG_EX_001="passed", ENG_EX_002="passed"))
    assert edit(root, PROD)[0]

    flow.green()
    flow.verify()
    assert edit(root, PROD)[0]
    assert sdd.load_state(root)["phase"] == "green"


@pytest.mark.spec("DEV-SDD-008")
@pytest.mark.parametrize(
    "path",
    [TEST, "apps/web/test/chatStream.test.ts", "packages/engine/src/shield_engine/testing.py"],
)
def test_test_edits_need_an_active_cycle(repo, path: str) -> None:
    root = repo()
    allowed, reason = edit(root, path)
    assert not allowed
    assert "sdd:start" in reason

    workflow(root).start("0042")
    assert edit(root, path)[0]


def test_docs_and_specs_are_always_editable(repo) -> None:
    root = repo()
    assert edit(root, "docs/README.md")[0]
    assert edit(root, "specs/0042-example/spec.md", old_string="x", new_string="y")[0]


@pytest.mark.spec("DEV-SDD-009")
@pytest.mark.parametrize("status", ["Accepted", "Implemented"])
def test_agents_cannot_accept_or_implement_specs_via_edit(repo, status: str) -> None:
    root = repo("Draft")

    allowed, reason = edit(
        root,
        "specs/0042-example/spec.md",
        old_string="- **Status:** Draft",
        new_string=f"- **Status:** {status}",
    )

    assert not allowed
    assert "human" in reason.lower()


@pytest.mark.spec("DEV-SDD-009")
def test_agents_cannot_accept_specs_via_write(repo) -> None:
    root = repo("Draft")
    content = (root / "specs/0042-example/spec.md").read_text().replace("Draft", "Accepted")

    allowed, _ = sdd.guard_edit(
        root, "Write", {"file_path": str(root / "specs/0042-example/spec.md"), "content": content}
    )

    assert not allowed


@pytest.mark.spec("DEV-SDD-009")
def test_new_specs_can_be_written_as_drafts(repo) -> None:
    root = repo()
    target = root / "specs/0043-new/spec.md"

    assert sdd.guard_edit(
        root, "Write", {"file_path": str(target), "content": "- **Status:** Draft"}
    )[0]
    assert not sdd.guard_edit(
        root, "Write", {"file_path": str(target), "content": "- **Status:** Accepted"}
    )[0]


# --- refactor mode ----------------------------------------------------------------


@pytest.mark.spec("DEV-SDD-010")
def test_refactor_mode_unlocks_production_but_still_needs_the_gate(repo) -> None:
    root = repo()
    flow = workflow(root, gate=True)
    flow.start_refactor("extract helper")

    assert edit(root, PROD)[0]
    with pytest.raises(SddError, match="sdd:verify"):
        flow.done()

    flow.verify()
    before = (root / "specs/0042-example/spec.md").read_text()
    message = flow.done()

    assert "extract helper" in message
    assert (root / "specs/0042-example/spec.md").read_text() == before
    assert sdd.load_state(root) is None


def test_refactor_mode_requires_a_reason(repo) -> None:
    with pytest.raises(SddError, match="reason"):
        workflow(repo()).start_refactor("  ")


# --- guard: stop -----------------------------------------------------------------


@pytest.mark.spec("DEV-SDD-011")
def test_stop_is_blocked_mid_cycle_with_the_next_command(repo) -> None:
    root = repo()
    to_red(root)

    blocked, reason = sdd.guard_stop(root, {"stop_hook_active": False})

    assert blocked
    assert "sdd:green" in reason


@pytest.mark.spec("DEV-SDD-011")
def test_stop_is_never_blocked_twice_or_without_a_cycle(repo) -> None:
    root = repo()
    assert not sdd.guard_stop(root, {"stop_hook_active": False})[0]

    to_red(root)
    assert not sdd.guard_stop(root, {"stop_hook_active": True})[0]


def test_stop_is_allowed_while_a_spec_awaits_review(repo) -> None:
    root = repo()
    workflow(root).start("0042")

    assert not sdd.guard_stop(root, {"stop_hook_active": False})[0]


# --- guard: bash (best effort) -------------------------------------------------


def test_shell_writes_to_production_are_denied_before_red(repo) -> None:
    root = repo()

    allowed, _ = sdd.guard_bash(root, f"sed -i '' 's/a/b/' {PROD}")
    assert not allowed
    assert sdd.guard_bash(root, f"cat {PROD}")[0]
    assert sdd.guard_bash(root, "uv run pytest")[0]
