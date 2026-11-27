"""Run the production-like load lab and find where the game breaks (lab only).

Usage: uv run python perf/prodsim/run.py [25 50 100 ...]

1. Make lab players, build and start the gateway and Redis containers (compose.yaml).
2. Limit the local Supabase database container to Supabase Nano (0.5 GB) for the run.
3. Run the swarm at each user level for LAB_DURATION, sample CPU and memory, and stop
   after the first level that breaks.
4. Restore the database limits, stop the lab and remove the lab players.

A level breaks when more than 1% of requests fail, or the health canary p95 passes 1 s
(something froze the gateway), or Easy runs p95 pass 5 s.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

LAB = Path(__file__).resolve().parent
ROOT = LAB.parents[1]
OUT = LAB / "out"
DB_CONTAINER = "supabase_db_ai-shield"
GATEWAY = "ai-shield-prodsim-gateway-1"
REDIS = "ai-shield-prodsim-redis-lab-1"
LEVELS = [int(a) for a in sys.argv[1:]] or [25, 50, 100, 200, 400, 800]
DURATION = os.environ.get("LAB_DURATION", "60s")

sys.path.insert(0, str(ROOT / "apps" / "api" / "tests" / "db"))
from conftest import local_stack  # noqa: E402


def sh(*args: str, env: dict[str, str] | None = None, check: bool = True) -> str:
    exe = shutil.which(args[0]) or args[0]
    result = subprocess.run(  # noqa: S603 - fixed commands of this lab
        [exe, *args[1:]], capture_output=True, text=True, env=env, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed:\n{result.stderr[-2000:]}")
    return result.stdout


def limits(container: str) -> tuple[int, int, int]:
    raw = json.loads(sh("docker", "inspect", container))[0]["HostConfig"]
    return int(raw["NanoCpus"]), int(raw["Memory"]), int(raw["MemorySwap"])


class Sampler:
    """Peak CPU and memory of the gateway and the database while a level runs."""

    def __init__(self) -> None:
        self.peak: dict[str, dict[str, float]] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            out = sh(
                "docker", "stats", "--no-stream", "--format",
                "{{.Name}} {{.CPUPerc}} {{.MemUsage}}", GATEWAY, DB_CONTAINER, check=False,
            )  # fmt: skip
            for line in out.splitlines():
                name, cpu, mem = line.split(" ", 2)
                used = mem.split(" / ")[0]
                mib = float(used[:-3]) * (1024 if used.endswith("GiB") else 1)
                peak = self.peak.setdefault(name, {"cpu_pct": 0.0, "mem_mib": 0.0})
                peak["cpu_pct"] = max(peak["cpu_pct"], float(cpu.rstrip("%")))
                peak["mem_mib"] = max(peak["mem_mib"], mib)
            time.sleep(2)

    def __enter__(self) -> Sampler:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=10)


def redis_command_stats() -> dict[str, int]:
    stats: dict[str, int] = {}
    for line in sh("docker", "exec", REDIS, "redis-cli", "info", "commandstats").splitlines():
        if line.startswith("cmdstat_"):
            name, rest = line.split(":", 1)
            stats[name.removeprefix("cmdstat_")] = int(rest.split(",")[0].split("=")[1])
    return stats


def redis_commands() -> int:
    for line in sh("docker", "exec", REDIS, "redis-cli", "info", "stats").splitlines():
        if line.startswith("total_commands_processed:"):
            return int(line.split(":")[1])
    return 0


def run_level(vus: int, env: dict[str, str]) -> dict[str, Any]:
    (OUT / "stalls.log").write_text("")
    before = redis_commands()
    before_stats = redis_command_stats()
    with Sampler() as sampler:
        k6 = subprocess.run(  # noqa: S603 - the pinned k6 binary
            [shutil.which("k6") or "k6", "run", "--quiet", str(LAB / "swarm.js")],
            env={**env, "LAB_VUS": str(vus), "LAB_DURATION": DURATION},
            capture_output=True,
            text=True,
            check=False,
        )
    (OUT / f"k6-{vus}.log").write_text(k6.stdout + k6.stderr)
    report = json.loads((OUT / f"k6-{vus}.json").read_text())
    stalls = (OUT / "stalls.log").read_text().count("--- stall")
    lag = json.loads((OUT / "lag.json").read_text()) if (OUT / "lag.json").exists() else {}
    report.update(
        stalls=stalls,
        max_loop_lag_ms=round(lag.get("max_lag_ms", 0.0)),
        redis_commands=redis_commands() - before,
        redis_by_command={
            k: v - before_stats.get(k, 0)
            for k, v in sorted(redis_command_stats().items(), key=lambda kv: -kv[1])
            if v - before_stats.get(k, 0) > 0
        },
        peaks=sampler.peak,
    )
    endpoints = report["endpoints"]
    fail_rate = report["unexpected"] / max(report["requests"], 1)
    canary = endpoints["health_canary"] or {}
    easy = endpoints["easy_run"] or {}
    reasons = []
    if fail_rate > 0.01:
        reasons.append(f"{fail_rate:.1%} of requests failed")
    if (canary.get("p95") or 0) > 1000:
        reasons.append(f"health canary p95 {canary['p95']:.0f} ms (gateway frozen)")
    if (easy.get("p95") or 0) > 5000:
        reasons.append(f"Easy run p95 {easy['p95']:.0f} ms")
    report["broken"] = reasons
    return report


def main() -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "stalls.log").write_text("")
    stack = local_stack()
    secret = secrets.token_urlsafe(32)
    env = {
        **os.environ,
        "LAB_PROXY_SECRET": secret,
        "LAB_SUPABASE_KEY": stack.service_key,
        "LAB_USERS": str(OUT / "users.json"),
        "LAB_OUT": str(OUT),
    }
    py = sys.executable
    print("making lab players ...", flush=True)
    sh(py, str(LAB / "seed.py"), "clean")
    sh(py, str(LAB / "seed.py"), "create", str(max(LEVELS)))
    print("starting the lab containers ...", flush=True)
    sh(
        "docker",
        "compose",
        "-f",
        str(LAB / "compose.yaml"),
        "up",
        "-d",
        "--build",
        "--wait",
        env=env,
    )
    for _ in range(60):
        if (
            sh(
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "http://127.0.0.1:8001/api/v1/health",
                check=False,
            )
            == "200"
        ):
            break
        time.sleep(1)
    original = limits(DB_CONTAINER)
    results: list[dict[str, Any]] = []
    try:
        # Supabase Nano: up to 0.5 GB on a shared CPU.
        sh(
            "docker",
            "update",
            "--cpus",
            "1",
            "--memory",
            "512m",
            "--memory-swap",
            "512m",
            DB_CONTAINER,
        )
        for vus in LEVELS:
            print(f"level {vus} users for {DURATION} ...", flush=True)
            result = run_level(vus, env)
            results.append(result)
            (OUT / "report.json").write_text(json.dumps(results, indent=2))
            print(
                f"  requests {result['requests']}, unexpected {result['unexpected']}, "
                f"rate limited {result['rate_limited']}, stalls {result['stalls']}, "
                f"max loop lag {result['max_loop_lag_ms']} ms, broken: {result['broken'] or 'no'}",
                flush=True,
            )
            if result["broken"]:
                break
    finally:
        # Docker cannot clear a limit, so "no limit" becomes the whole machine.
        cpus, memory, _ = original
        host = json.loads(sh("docker", "info", "--format", "{{json .}}"))
        sh(
            "docker", "update",
            "--cpus", str(cpus / 1e9 if cpus else host["NCPU"]),
            "--memory", str(memory or host["MemTotal"]),
            "--memory-swap", str(2 * (memory or host["MemTotal"])), DB_CONTAINER, check=False,
        )  # fmt: skip
        print(f"database limits restored to {limits(DB_CONTAINER)}", flush=True)
        sh("docker", "compose", "-f", str(LAB / "compose.yaml"), "down", env=env, check=False)
        sh(py, str(LAB / "seed.py"), "clean", check=False)


if __name__ == "__main__":
    main()
