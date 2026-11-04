"""Enforced spec-driven + test-driven lifecycle (spec 0010).

    spec ──sdd:red──▶ red ──sdd:green──▶ green ──sdd:verify──▶ verified ──sdd:done──▶ ∅
    (refactor mode: refactor ──sdd:verify──▶ verified ──sdd:done──▶ ∅)

Every transition checks real evidence. The same module backs the Claude Code
hooks that stop agents from skipping steps: ``python3 scripts/sdd.py hook …``.
Standard library only, so hooks start fast.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = Path(".sdd/state.json")

CRITERION = re.compile(r"^- \*\*([A-Z]{2,5}-[A-Z]{2,10}-\d{3})\*\*", re.MULTILINE)
STATUS_LINE = re.compile(r"^(- \*\*Status:\*\*[ \t]*)(.*)$", re.MULTILINE)
PROTECTED_STATUSES = {"Accepted", "Implemented"}

TEST_PATHS = re.compile(
    r"(^|/)tests/|^apps/web/test/|^packages/engine/src/shield_engine/testing\.py$"
)
PRODUCTION_PATHS = re.compile(
    r"^(packages/[^/]+/src/|apps/api/src/|apps/web/app/|supabase/migrations/)"
)
PRODUCTION_IN_COMMAND = re.compile(
    r"(packages/[\w-]+/src/|apps/api/src/|apps/web/app/|supabase/migrations/)"
)
SHELL_WRITE = re.compile(
    r"(>|\btee\b|\bsed\s+-i|\bperl\s+-\w*i|\bmv\b|\bcp\b|\brm\b|write_text|open\([^)]*['\"][wa])"
)
LEGIT_PY_ERROR = re.compile(
    r"(ImportError|ModuleNotFoundError|AttributeError)[^\n]*\b(shield_engine|shield_api)\b"
)
LEGIT_TS_ERROR = re.compile(
    r"does not provide an export named|is not exported by|"
    r"(Failed to resolve import|Cannot find module) ['\"](\.\./app/|~/)"
)

EDIT_PHASES = {"red", "green", "verified", "refactor"}
STOP_PHASES = {"red", "green", "verified"}
NEXT_STEP = {
    "spec": "write failing tests for the target criteria, then `mise run sdd:red`",
    "red": "implement the minimum code, then `mise run sdd:green`",
    "green": "`mise run sdd:verify` (runs the full gate)",
    "refactor": "`mise run sdd:verify` (runs the full gate)",
    "verified": "`mise run sdd:done` (records verification in the spec)",
}
REACHED_BY = {
    "spec": "`mise run sdd:start`",
    "red": "`mise run sdd:red`",
    "green": "`mise run sdd:green`",
    "refactor": "`mise run sdd:start --refactor`",
    "verified": "`mise run sdd:verify`",
}
NO_CYCLE = (
    "No SDD cycle is active. Start one with `mise run sdd:start <spec-number> [IDs…]` "
    '(spec must be Accepted), or `mise run sdd:start --refactor "<reason>"` for a '
    "behaviour-preserving change."
)


class SddError(Exception):
    """A transition was refused. The message tells the agent what to do instead."""


@dataclass(frozen=True)
class TestOutcome:
    name: str
    status: Literal["passed", "failed", "error", "skipped"]
    message: str = ""


@dataclass
class TestRun:
    by_id: dict[str, list[TestOutcome]] = field(default_factory=dict)


Runner = Callable[[Path, list[str]], TestRun]
Gate = Callable[[Path], bool]


# --- state & specs --------------------------------------------------------------


def load_state(root: Path) -> dict[str, Any] | None:
    path = root / STATE_FILE
    if not path.exists():
        return None
    state: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return state


def save_state(root: Path, state: dict[str, Any] | None) -> None:
    path = root / STATE_FILE
    if state is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def find_spec(root: Path, number: str) -> Path:
    matches = sorted((root / "specs").glob(f"{number.zfill(4)}-*/spec.md"))
    if not matches:
        raise SddError(f"Spec {number} not found under specs/. Create it with `mise run spec:new`.")
    return matches[0]


def spec_status(text: str) -> str | None:
    match = STATUS_LINE.search(text)
    return match.group(2).strip() if match else None


def is_legitimate_collection_error(message: str) -> bool:
    """A test module that cannot import a production symbol that doesn't exist yet."""
    return bool(LEGIT_PY_ERROR.search(message) or LEGIT_TS_ERROR.search(message))


# --- the workflow ---------------------------------------------------------------


class Workflow:
    def __init__(
        self,
        root: Path = ROOT,
        *,
        runner: Runner | None = None,
        gate: Gate | None = None,
        commit: Callable[[], str] | None = None,
    ) -> None:
        self.root = root
        self.runner = runner or run_tests
        self.gate = gate or run_gate
        self.commit = commit or current_commit

    # transitions ----------------------------------------------------------------

    def start(self, number: str, ids: list[str] | None = None) -> str:
        self._refuse_if_busy()
        spec = find_spec(self.root, number)
        text = spec.read_text(encoding="utf-8")
        status = spec_status(text)
        if status not in PROTECTED_STATUSES:
            raise SddError(
                f"{spec.parent.name} is '{status}'. A human must set it to Accepted before "
                "implementation starts (or it must already be Implemented, for a fix)."
            )
        defined = CRITERION.findall(text)
        unknown = [i for i in ids or [] if i not in defined]
        if unknown:
            raise SddError(f"Not defined in {spec.parent.name}: {', '.join(unknown)}")
        targets = ids or defined
        if not targets:
            raise SddError(f"{spec.parent.name} defines no acceptance criteria.")
        save_state(
            self.root,
            {
                "mode": "spec",
                "phase": "spec",
                "spec": spec.parent.name,
                "ids": targets,
                "started": _now(),
            },
        )
        return (
            f"Cycle started for {spec.parent.name}: {', '.join(targets)}.\n"
            f"Next: {NEXT_STEP['spec']}"
        )

    def start_refactor(self, reason: str) -> str:
        if not reason.strip():
            raise SddError('Refactor mode needs a reason: `mise run sdd:start --refactor "…"`.')
        self._refuse_if_busy()
        save_state(
            self.root,
            {"mode": "refactor", "phase": "refactor", "reason": reason.strip(), "started": _now()},
        )
        return f"Refactor cycle started: {reason.strip()}\nNext: {NEXT_STEP['refactor']}"

    def red(self) -> str:
        state = self._expect("spec")
        run = self.runner(self.root, state["ids"])
        untested = [i for i in state["ids"] if not run.by_id.get(i)]
        if untested:
            raise SddError(f"No tests reference: {', '.join(untested)}. Write them first.")

        passing, broken, failing = [], [], []
        for criterion in state["ids"]:
            outcomes = run.by_id[criterion]
            failed = [o for o in outcomes if o.status == "failed"]
            if failed:
                failing.extend(failed)
            elif all(o.status == "passed" for o in outcomes):
                passing.append(criterion)
            else:
                broken.append(criterion)
        if passing:
            raise SddError(
                f"Tests for {', '.join(passing)} already pass, so they prove nothing. "
                "Tighten them until they fail against the current code."
            )
        if broken:
            raise SddError(
                f"Tests for {', '.join(broken)} error out instead of failing (syntax, fixture or "
                "unrelated import error). Red must be an assertion failure or a missing "
                "production symbol."
            )
        state.update(
            phase="red",
            red={"failed": len(failing), "examples": [o.name for o in failing[:3]], "at": _now()},
        )
        save_state(self.root, state)
        return f"RED confirmed: {len(failing)} failing test(s).\nNext: {NEXT_STEP['red']}"

    def green(self) -> str:
        state = self._expect("red", "green")
        run = self.runner(self.root, state["ids"])
        not_passing = sorted(
            {c for c in state["ids"] for o in run.by_id.get(c, []) if o.status != "passed"}
            | {c for c in state["ids"] if not run.by_id.get(c)}
        )
        if not_passing:
            raise SddError(f"Not green yet: {', '.join(not_passing)}. Keep implementing.")
        passed = sum(len(run.by_id[c]) for c in state["ids"])
        state.update(phase="green", green={"passed": passed, "at": _now()})
        save_state(self.root, state)
        return f"GREEN: {passed} passing test(s).\nNext: {NEXT_STEP['green']}"

    def verify(self) -> str:
        state = self._expect("green", "refactor")
        if not self.gate(self.root):
            raise SddError(
                "`mise run check` failed. Fix every failure, then run `mise run sdd:verify` again."
            )
        state.update(phase="verified", verified_at=_now())
        save_state(self.root, state)
        return f"VERIFIED: full gate passed.\nNext: {NEXT_STEP['verified']}"

    def done(self) -> str:
        state = self._expect("verified")
        save_state(self.root, None)
        if state["mode"] == "refactor":
            return f"Refactor complete and verified: {state['reason']}"

        spec = next((self.root / "specs").glob(f"{state['spec']}/spec.md"))
        text = STATUS_LINE.sub(r"\g<1>Implemented", spec.read_text(encoding="utf-8"), count=1)
        red, green = state["red"], state["green"]
        examples = ", ".join(f"`{name}`" for name in red["examples"])
        entry = (
            f"\n### {dt.date.today().isoformat()} · commit {self.commit()}\n\n"
            f"- Criteria: {', '.join(state['ids'])}\n"
            f"- Red: {red['failed']} failing test(s) before implementation ({examples})\n"
            f"- Green: {green['passed']} passing test(s)\n"
            "- Gate: `mise run check` passed\n"
        )
        if "\n## Verification" not in text:
            text = text.rstrip("\n") + "\n\n## Verification\n"
        spec.write_text(text.rstrip("\n") + "\n" + entry, encoding="utf-8")

        tasks = spec.with_name("tasks.md")
        if tasks.exists():
            content = tasks.read_text(encoding="utf-8")
            for criterion in state["ids"]:
                content = re.sub(
                    rf"^- \[ \] (\*\*{re.escape(criterion)}\*\*)", r"- [x] \1", content, flags=re.M
                )
            tasks.write_text(content, encoding="utf-8")
        return f"DONE: {state['spec']} is Implemented and the verification is recorded."

    def status(self) -> str:
        state = load_state(self.root)
        if state is None:
            return NO_CYCLE
        subject = state.get("spec") or f"refactor: {state.get('reason')}"
        ids = f" [{', '.join(state['ids'])}]" if state.get("ids") else ""
        phase = state["phase"]
        return f"SDD cycle: {subject}{ids}. Phase: {phase}.\nNext: {NEXT_STEP[phase]}"

    def abort(self) -> str:
        save_state(self.root, None)
        return "Cycle discarded. Nothing was recorded in the spec."

    # helpers ----------------------------------------------------------------------

    def _expect(self, *phases: str) -> dict[str, Any]:
        state = load_state(self.root)
        if state is None:
            raise SddError(NO_CYCLE)
        if state["phase"] not in phases:
            required = " or ".join(f"'{p}' (via {REACHED_BY[p]})" for p in phases)
            raise SddError(
                f"Phase is '{state['phase']}'; this step needs {required}. "
                f"Next: {NEXT_STEP[state['phase']]}"
            )
        return state

    def _refuse_if_busy(self) -> None:
        state = load_state(self.root)
        if state and state["phase"] not in {"spec"}:
            raise SddError(
                f"A cycle is already in phase '{state['phase']}'. Finish it "
                f"({NEXT_STEP[state['phase']]}) or discard it with `mise run sdd:abort`."
            )


# --- agent guards (Claude Code hooks) -------------------------------------------


def _relative(root: Path, file_path: str) -> str | None:
    try:
        return Path(file_path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def _new_content(tool_name: str, tool_input: dict[str, Any], current: str) -> str:
    if tool_name == "Write":
        return str(tool_input.get("content", ""))
    edits = tool_input.get("edits") or [tool_input]
    content = current
    for edit in edits:
        old, new = str(edit.get("old_string", "")), str(edit.get("new_string", ""))
        content = (
            content.replace(old, new) if edit.get("replace_all") else content.replace(old, new, 1)
        )
    return content


def _reopen(root: Path, state: dict[str, Any]) -> None:
    if state["phase"] == "verified":
        state["phase"] = "refactor" if state["mode"] == "refactor" else "green"
        save_state(root, state)


def guard_edit(root: Path, tool_name: str, tool_input: dict[str, Any]) -> tuple[bool, str]:
    relative = _relative(root, str(tool_input.get("file_path", "")))
    if relative is None:
        return True, ""

    if re.fullmatch(r"specs/[^/]+/spec\.md", relative):
        path = root / relative
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        before = spec_status(current)
        after = spec_status(_new_content(tool_name, tool_input, current))
        if after in PROTECTED_STATUSES and after != before:
            return False, (
                f"Agents may not set a spec to {after}. Accepting a spec is a human decision; "
                "`Implemented` is written only by `mise run sdd:done`. Ask the user to review it."
            )
        return True, ""

    is_test = bool(TEST_PATHS.search(relative))
    is_production = not is_test and bool(PRODUCTION_PATHS.search(relative))
    if not (is_test or is_production):
        return True, ""

    state = load_state(root)
    if state is None:
        return False, NO_CYCLE
    if is_production and state["phase"] not in EDIT_PHASES:
        return False, (
            f"Production code is locked until RED is confirmed (phase '{state['phase']}'). "
            f"Next: {NEXT_STEP[state['phase']]}"
        )
    _reopen(root, state)
    return True, ""


def guard_bash(root: Path, command: str) -> tuple[bool, str]:
    """Best effort: catch obvious shell writes to production files before RED."""
    if not (PRODUCTION_IN_COMMAND.search(command) and SHELL_WRITE.search(command)):
        return True, ""
    state = load_state(root)
    if state is None:
        return False, NO_CYCLE
    if state["phase"] not in EDIT_PHASES:
        return False, (
            f"This command appears to write production code, which is locked in phase "
            f"'{state['phase']}'. Next: {NEXT_STEP[state['phase']]}"
        )
    _reopen(root, state)
    return True, ""


def guard_stop(root: Path, payload: dict[str, Any]) -> tuple[bool, str]:
    if payload.get("stop_hook_active"):
        return False, ""
    state = load_state(root)
    if state is None or state["phase"] not in STOP_PHASES:
        return False, ""
    return True, (
        f"SDD cycle for {state.get('spec') or state.get('reason')} is unfinished (phase "
        f"'{state['phase']}'). Next: {NEXT_STEP[state['phase']]}. Finish the cycle, or tell the "
        "user exactly why you are stopping (they can discard it with `mise run sdd:abort`)."
    )


# --- real runners ------------------------------------------------------------------


def _ids_in_file(path: Path, wanted: set[str]) -> set[str]:
    try:
        return {i for i in wanted if i in path.read_text(encoding="utf-8")}
    except OSError:
        return set()


def _run_python(root: Path, ids: list[str], run: TestRun) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        subprocess.run(
            ["uv", "run", "--quiet", "pytest", "-q", "-p", "no:cacheprovider",
             "--continue-on-collection-errors", "--no-cov",
             f"--spec-ids={','.join(ids)}", f"--spec-report={report}"],
            cwd=root, check=False,
        )  # fmt: skip
        if not report.exists():
            raise SddError("pytest produced no report; see its output above.")
        data = json.loads(report.read_text(encoding="utf-8"))
    for item in data["items"]:
        for criterion in item["ids"]:
            run.by_id.setdefault(criterion, []).append(
                TestOutcome(item["nodeid"], item["outcome"], item.get("message", ""))
            )
    for error in data["collect_errors"]:
        status = "failed" if is_legitimate_collection_error(error["message"]) else "error"
        for criterion in error["ids"]:
            run.by_id.setdefault(criterion, []).append(
                TestOutcome(error["path"], status, error["message"])
            )


def _run_web(root: Path, ids: list[str], run: TestRun) -> None:
    web = root / "apps" / "web"
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "vitest.json"
        pattern = "|".join(re.escape(f"[{i}]") for i in ids)
        subprocess.run(
            ["bunx", "vitest", "run", "--reporter=default", "--reporter=json",
             f"--outputFile.json={report}", "-t", pattern],
            cwd=web, check=False,
        )  # fmt: skip
        if not report.exists():
            raise SddError("vitest produced no report; see its output above.")
        data = json.loads(report.read_text(encoding="utf-8"))
    wanted = set(ids)
    for suite in data.get("testResults", []):
        assertions = suite.get("assertionResults", [])
        if not assertions and suite.get("status") == "failed":
            message = suite.get("message", "")
            status = "failed" if is_legitimate_collection_error(message) else "error"
            for criterion in _ids_in_file(Path(suite["name"]), wanted):
                run.by_id.setdefault(criterion, []).append(
                    TestOutcome(suite["name"], status, message)
                )
        for test in assertions:
            for criterion in wanted:
                if f"[{criterion}]" in test["fullName"] and test["status"] != "pending":
                    outcome = (
                        test["status"] if test["status"] in {"passed", "failed"} else "skipped"
                    )
                    run.by_id.setdefault(criterion, []).append(
                        TestOutcome(test["fullName"], outcome)
                    )


def run_tests(root: Path, ids: list[str]) -> TestRun:
    run = TestRun()
    python_ids = [i for i in ids if not i.startswith("WEB-")]
    web_ids = [i for i in ids if i.startswith("WEB-")]
    if python_ids:
        _run_python(root, python_ids, run)
    if web_ids:
        _run_web(root, web_ids, run)
    return run


def run_gate(root: Path) -> bool:
    return subprocess.run(["mise", "run", "check"], cwd=root, check=False).returncode == 0


def current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    sha = result.stdout.strip() or "uncommitted"
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    return f"{sha} (+ uncommitted changes)" if dirty else sha


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


# --- CLI ------------------------------------------------------------------------------


def _hook(event: str, root: Path) -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    if event == "pre-tool":
        tool, tool_input = payload.get("tool_name", ""), payload.get("tool_input", {})
        if tool == "Bash":
            allowed, reason = guard_bash(root, str(tool_input.get("command", "")))
        elif tool in {"Edit", "Write", "MultiEdit"}:
            allowed, reason = guard_edit(root, tool, tool_input)
        else:
            allowed, reason = True, ""
        if not allowed:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"[SDD] {reason}",
            }}))  # fmt: skip
    elif event == "stop":
        blocked, reason = guard_stop(root, payload)
        if blocked:
            print(json.dumps({"decision": "block", "reason": f"[SDD] {reason}"}))
    elif event == "session-start":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "[SDD] " + Workflow(root).status()
            + "\nThis repo enforces spec → red → green → verified → done (see AGENTS.md).",
        }}))  # fmt: skip
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sdd", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="start a cycle for an Accepted spec")
    start.add_argument("spec", nargs="?")
    start.add_argument("ids", nargs="*")
    start.add_argument("--refactor", metavar="REASON")
    for name in ("red", "green", "verify", "done", "status", "abort"):
        sub.add_parser(name)
    hook = sub.add_parser("hook")
    hook.add_argument("event", choices=["pre-tool", "stop", "session-start"])
    args = parser.parse_args(argv)

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or ROOT)
    if args.command == "hook":
        return _hook(args.event, root)

    flow = Workflow(root)
    try:
        if args.command == "start":
            if args.refactor is not None:
                message = flow.start_refactor(args.refactor)
            elif not args.spec:
                raise SddError("Usage: mise run sdd:start <spec-number> [IDs…]")
            else:
                message = flow.start(args.spec, args.ids or None)
        else:
            message = getattr(flow, args.command)()
    except SddError as error:
        print(f"✗ {error}", file=sys.stderr)
        return 1
    print(f"✓ {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
