"""Persistent subprocess worker that keeps scikit-learn warm and isolates fits."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from collections.abc import Mapping
from contextlib import suppress

from shield_engine.game import BoardValidationError, fit_classifier, sign_model

_STARTUP_TIMEOUT_SECONDS = 15.0
# The only parent variables a training child sees; keys and secrets stay out (spec 0054).
WORKER_ENV_ALLOWLIST = ("PATH", "PYTHONPATH", "PYTHONUNBUFFERED", "HOME", "TMPDIR", "LANG")


def worker_environment(parent: Mapping[str, str]) -> dict[str, str]:
    return {name: parent[name] for name in WORKER_ENV_ALLOWLIST if name in parent}


_STREAM_LIMIT_BYTES = 4 * 1024 * 1024


class TrainWorkerRunner:
    """Manage one warm training child process across fits, killing it on timeout."""

    def __init__(self, *, startup_timeout_seconds: float = _STARTUP_TIMEOUT_SECONDS) -> None:
        self._startup_timeout_seconds = startup_timeout_seconds
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock: asyncio.Lock | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._cmd: tuple[str, ...] | None = None

    @property
    def pid(self) -> int | None:
        if self._proc is None or self._proc.returncode is not None:
            return None
        return self._proc.pid

    async def aclose(self) -> None:
        proc = self._proc
        loop = self._loop
        self._proc = None
        self._cmd = None
        if proc is None:
            return
        with suppress(ProcessLookupError):
            proc.kill()
        with suppress(RuntimeError):
            if loop is asyncio.get_running_loop():
                await proc.wait()

    async def _ensure_started(self, cmd: tuple[str, ...]) -> asyncio.subprocess.Process:
        if self._proc is not None and (self._cmd != cmd or self._proc.returncode is not None):
            await self.aclose()
        if self._proc is not None:
            return self._proc

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=_STREAM_LIMIT_BYTES,
            env=worker_environment(os.environ),
        )
        try:
            assert proc.stdout is not None
            ready_raw = await asyncio.wait_for(
                proc.stdout.readline(), timeout=self._startup_timeout_seconds
            )
            if not ready_raw:
                assert proc.stderr is not None
                err_out = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"Training worker exited before ready: {err_out or 'no output'}")
            ready = json.loads(ready_raw.decode("utf-8"))
            if not isinstance(ready, dict) or not ready.get("ready"):
                raise RuntimeError("Training worker sent an invalid readiness handshake.")
        except BaseException:
            with suppress(ProcessLookupError):
                proc.kill()
            with suppress(Exception):
                await proc.wait()
            raise
        self._proc = proc
        self._cmd = cmd
        return proc

    async def run(
        self,
        *,
        cmd: tuple[str, ...],
        algorithm: str,
        rows: list[tuple[str, int]],
        max_rows: int,
        signing_key: bytes,
        context: bytes,
        timeout_seconds: float,
    ) -> tuple[str, int, float, bytes]:
        loop = asyncio.get_running_loop()
        if self._loop is not loop or self._lock is None:
            await self.aclose()
            self._loop = loop
            self._lock = asyncio.Lock()

        request_line = (
            json.dumps(
                {
                    "algorithm": algorithm,
                    "rows": rows,
                    "max_rows": max_rows,
                    "signing_key_b64": base64.b64encode(signing_key).decode("ascii"),
                    "context_b64": base64.b64encode(context).decode("ascii"),
                }
            )
            + "\n"
        ).encode("utf-8")

        async with self._lock:
            proc = await self._ensure_started(cmd)
            assert proc.stdin is not None
            assert proc.stdout is not None
            try:
                proc.stdin.write(request_line)
                await proc.stdin.drain()
                resp_raw = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout_seconds)
            except BaseException:
                await self.aclose()
                raise

            if not resp_raw:
                assert proc.stderr is not None
                msg = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
                await self.aclose()
                raise RuntimeError(f"Training worker crashed: {msg or 'unexpected EOF'}")

            out = json.loads(resp_raw.decode("utf-8"))
            if not out.get("ok"):
                raise BoardValidationError(str(out.get("error", "Invalid training dataset.")))
            return (
                str(out["algorithm"]),
                int(out["sample_count"]),
                float(out["accuracy"]),
                base64.b64decode(str(out["blob_b64"])),
            )


def main() -> int:
    """Load ML imports once, signal readiness, and serve fit requests over stdio."""
    sys.stdout.buffer.write(b'{"ready":true}\n')
    sys.stdout.buffer.flush()
    while raw_line := sys.stdin.buffer.readline():
        stripped = raw_line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped.decode("utf-8"))
        algorithm = str(payload["algorithm"])
        rows = [(str(item[0]), int(item[1])) for item in payload["rows"]]
        max_rows = int(payload["max_rows"])
        signing_key = base64.b64decode(str(payload["signing_key_b64"]))
        context = base64.b64decode(str(payload["context_b64"]))
        try:
            fitted = fit_classifier(algorithm=algorithm, rows=rows, max_rows=max_rows)
            blob = sign_model(fitted.model, key=signing_key, context=context)
            response: dict[str, object] = {
                "ok": True,
                "algorithm": fitted.algorithm,
                "sample_count": fitted.sample_count,
                "accuracy": fitted.accuracy,
                "blob_b64": base64.b64encode(blob).decode("ascii"),
            }
        except BoardValidationError as err:
            response = {"ok": False, "error": str(err)}
        sys.stdout.buffer.write((json.dumps(response) + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
