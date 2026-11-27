"""k6 load tests: safe targets, model-free payloads, SLOs and redacted reports (spec 0057).

The run tests start the gateway in-process with in-memory stores (`perf/k6/serve_api.py`), so
they need only the k6 binary that `mise.toml` pins. Without k6 on PATH they are skipped.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
K6_DIR = ROOT / "perf" / "k6"
SCENARIOS = ("smoke", "load", "spike", "stress", "soak")
SECRET = "k6-proxy-secret-" + "x" * 24
K6 = shutil.which("k6")
needs_k6 = pytest.mark.skipif(K6 is None, reason="k6 is not on PATH; run through mise")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _serve(mode: str) -> Iterator[str]:
    if not (K6_DIR / "serve_api.py").exists():
        yield ""
        return
    port = _free_port()
    env = {**os.environ, "SHIELD_K6_PROXY_SECRET": SECRET}
    proc = subprocess.Popen(
        [sys.executable, str(K6_DIR / "serve_api.py"), "--mode", mode, "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                headers = {"x-shield-proxy-secret": SECRET}
                health = f"{url}/api/v1/health"  # always http://127.0.0.1
                request = urllib.request.Request(health, headers=headers)  # noqa: S310
                with urllib.request.urlopen(request, timeout=1) as res:  # noqa: S310 - loopback
                    if res.status == 200:
                        break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("the gateway did not start")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture
def dev_api() -> Iterator[str]:
    yield from _serve("dev")


@pytest.fixture
def prod_api() -> Iterator[str]:
    yield from _serve("prod")


def _k6(
    scenario: str, target: str, tmp: Path, **env: str
) -> tuple[subprocess.CompletedProcess[str], dict[str, object] | None]:
    assert K6 is not None
    assert target, "no gateway to test (perf/k6/serve_api.py is missing)"
    report = tmp / f"{scenario}-summary.json"
    run_env = {
        **os.environ,
        "K6_TARGET_URL": target,
        "K6_REPORT_DIR": str(tmp),
        "K6_NO_USAGE_REPORT": "true",
        **env,
    }
    result = subprocess.run(
        [K6, "run", "--quiet", str(K6_DIR / "scenarios" / f"{scenario}.js")],
        cwd=ROOT,
        env=run_env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    data = json.loads(report.read_text()) if report.exists() else None
    return result, data


def _node(code: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node") or shutil.which("bun")
    assert node is not None
    return subprocess.run(
        [node, "--input-type=module", "-e", code] if node.endswith("node") else [node, "-e", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.spec("DEV-LOAD-001")
def test_remote_targets_need_an_explicit_opt_in() -> None:
    code = (
        "import { resolveTarget } from './perf/k6/lib/config.js';"
        "const out = [];"
        "for (const [url, allow] of [['https://example.com', ''], ['http://127.0.0.1:8000', ''],"
        " ['http://localhost:3000', ''], ['http://[::1]:8000', ''],"
        " ['https://example.com', '1']]) {"
        "  try { out.push(resolveTarget(url, allow)); } catch (e) { out.push('refused'); } }"
        "console.log(JSON.stringify(out));"
    )
    result = _node(code)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        "refused",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://[::1]:8000",
        "https://example.com",
    ]


@needs_k6
@pytest.mark.spec("DEV-LOAD-001")
def test_k6_aborts_before_sending_load_to_a_remote_target(tmp_path: Path) -> None:
    result, _ = _k6("smoke", "https://example.com", tmp_path)
    assert result.returncode != 0
    assert "K6_ALLOW_REMOTE" in result.stderr + result.stdout


@pytest.mark.spec("DEV-LOAD-002")
def test_payloads_are_model_free_and_send_no_provider_keys() -> None:
    sources = "\n".join(p.read_text() for p in K6_DIR.rglob("*.js"))
    kinds = set(re.findall(r"kind:\s*'([a-z_]+)'", sources))
    assert kinds
    assert kinds <= {"incoming", "assistant", "word_filter", "length_limit", "text_cleanup"}
    for banned in (
        "api_key",
        "billing/checkout",
        "safety_check",
        "llm_review",
        "'jev'",
        "'custom'",
    ):
        assert banned not in sources, banned
    assert set(re.findall(r"level_id:\s*'([a-z0-9-]+)'", sources)) <= {"easy-1", "easy-2"}


@needs_k6
@pytest.mark.spec("DEV-LOAD-003")
def test_smoke_passes_every_check_and_threshold(dev_api: str, tmp_path: Path) -> None:
    result, summary = _k6("smoke", dev_api, tmp_path, K6_SMOKE_DURATION="6s")
    assert result.returncode == 0, result.stderr[-3000:]
    assert summary is not None
    for name in ("health", "levels", "leaderboard", "anonymous", "progress", "game_run"):
        assert name in json.dumps(summary["checks"]), name
    assert summary["thresholds_ok"] is True


@needs_k6
@pytest.mark.spec("DEV-LOAD-004")
def test_leaderboard_spike_meets_its_latency_slo(dev_api: str, tmp_path: Path) -> None:
    result, summary = _k6("spike", dev_api, tmp_path, K6_SPIKE_DURATION="8s")
    assert result.returncode == 0, result.stderr[-3000:]
    assert summary is not None
    board = summary["metrics"]["leaderboard"]
    assert board["p95"] < 200
    assert board["p99"] < 500
    assert summary["metrics"]["unexpected_5xx"] == 0


@needs_k6
@pytest.mark.spec("DEV-LOAD-005")
def test_stress_counts_429s_as_expected_and_never_5xx(prod_api: str, tmp_path: Path) -> None:
    result, summary = _k6(
        "stress", prod_api, tmp_path, K6_PROXY_SECRET=SECRET, K6_STRESS_DURATION="8s"
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert summary is not None
    assert summary["metrics"]["rate_limited"] > 0
    assert summary["metrics"]["unexpected_5xx"] == 0
    assert summary["metrics"]["health"]["p95"] < 50


@needs_k6
@pytest.mark.spec("DEV-LOAD-006")
def test_summary_holds_no_cookies_tokens_or_secrets(prod_api: str, tmp_path: Path) -> None:
    result, summary = _k6(
        "smoke", prod_api, tmp_path, K6_PROXY_SECRET=SECRET, K6_SMOKE_DURATION="4s"
    )
    assert summary is not None, result.stderr[-3000:]
    text = (tmp_path / "smoke-summary.json").read_text()
    assert SECRET not in text
    assert SECRET not in result.stdout + result.stderr
    for marker in ("shield_player_session", "x-shield-proxy-secret", "set-cookie", "token"):
        assert marker not in text.lower(), marker
    assert "http_req_duration" in json.dumps(summary["metrics"]) or summary["metrics"]


@pytest.mark.spec("DEV-LOAD-007")
def test_perf_tasks_and_the_load_workflow() -> None:
    tasks = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]
    for scenario in SCENARIOS:
        assert f"scenarios/{scenario}.js" in str(tasks[f"perf:{scenario}"]["run"]), scenario
    check = str(tasks["perf:check"]["run"])
    assert "k6 inspect" in check
    for scenario in SCENARIOS:
        assert (K6_DIR / "scenarios" / f"{scenario}.js").exists()
    assert ".reports" in (ROOT / ".gitignore").read_text()

    text = (ROOT / ".github" / "workflows" / "load.yml").read_text()
    workflow = yaml.safe_load(text)
    assert "workflow_dispatch" in workflow[True]
    for use in re.findall(r"uses:\s*(\S+)", text):
        if not use.startswith("./"):
            assert re.search(r"@[0-9a-f]{40}$", use), use
    actionlint = shutil.which("actionlint")
    if actionlint:
        lint = subprocess.run(
            [actionlint, str(ROOT / ".github" / "workflows" / "load.yml")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert lint.returncode == 0, lint.stdout
