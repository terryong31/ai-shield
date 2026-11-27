"""The gateway as production runs it, inside a container sized like one Vercel Hobby
function (1 vCPU, 2 GB). Lab only: it is never deployed.

It builds the real container (Supabase stores, Redis, rate limits, BotID and the proxy
secret on), swaps the AI models for a fake with realistic latency, and starts a watchdog
thread that records every stall of the event loop with the stack that caused it.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import threading
import time
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import uvicorn

from shield_api.container import build_container
from shield_api.main import create_app
from shield_api.settings import Settings
from shield_engine.ports import ChatCompletion

OUT = Path(os.environ.get("LAB_OUT", "/lab/out"))
STALL_MS = float(os.environ.get("LAB_STALL_MS", "200"))


class FakeModel:
    """An async chat model that answers like the agent after 0.6 to 2.5 seconds."""

    async def complete_with_usage(
        self,
        messages: Sequence[Any],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        thinking: bool = False,
    ) -> ChatCompletion:
        await asyncio.sleep(random.uniform(0.6, 2.5))  # noqa: S311 - latency jitter
        reply = {"reply": "Here is what I found.", "tool_calls": [], "refused": False}
        return ChatCompletion(text=json.dumps(reply), input_tokens=900, output_tokens=120)


class Watchdog:
    """A heartbeat on the event loop, checked from a thread. A late beat is a stall."""

    def __init__(self, loop: asyncio.AbstractEventLoop, main_ident: int) -> None:
        self.loop = loop
        self.main_ident = main_ident
        self.last = time.monotonic()
        self.max_lag_ms = 0.0
        self.reported = 0.0

    def beat(self) -> None:
        now = time.monotonic()
        self.last = now
        self.loop.call_later(0.05, self.beat)

    def watch(self) -> None:
        log = OUT / "stalls.log"
        while True:
            time.sleep(0.05)
            lag_ms = (time.monotonic() - self.last) * 1000 - 50
            self.max_lag_ms = max(self.max_lag_ms, lag_ms)
            if lag_ms > STALL_MS and time.monotonic() - self.reported > 1.0:
                self.reported = time.monotonic()
                frame = sys._current_frames().get(self.main_ident)
                stack = "".join(traceback.format_stack(frame)) if frame else "(no frame)"
                with log.open("a") as fh:
                    fh.write(f"--- stall {lag_ms:.0f} ms at {time.time():.3f}\n{stack}\n")
            (OUT / "lag.json").write_text(json.dumps({"max_lag_ms": self.max_lag_ms}))


def build() -> Any:
    dev = Settings(APP_ENV="development")
    container = build_container(dev)
    # Production rules on every request: rate limits, BotID, the proxy secret, headers.
    container.settings = Settings(
        APP_ENV="production",
        SESSION_COOKIE_SECURE=False,
        TRUSTED_PROXY_SECRET=os.environ["LAB_PROXY_SECRET"],
        TRUSTED_CLIENT_IP_HEADER="x-shield-client-ip",
        MODEL_SIGNING_KEY="lab-signing-key-" + "k" * 32,
        WEB_BASE_URL="https://ai-shield.lab",
        SUPABASE_URL=dev.SUPABASE_URL,
        SUPABASE_KEY=dev.SUPABASE_KEY,
        REDIS_URL=dev.REDIS_URL,
    )
    container.model_signing_key = b"lab-signing-key-" + b"k" * 32
    container.game_agents = {"standard": FakeModel(), "budget": FakeModel()}  # type: ignore[dict-item]
    container.game_agent = FakeModel()  # type: ignore[assignment]
    return create_app(container)


async def main() -> None:
    app = build()
    loop = asyncio.get_running_loop()
    dog = Watchdog(loop, threading.main_thread().ident or 0)
    dog.beat()
    threading.Thread(target=dog.watch, daemon=True).start()
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")  # noqa: S104
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stalls.log").write_text("")
    asyncio.run(main())
