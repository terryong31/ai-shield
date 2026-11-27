"""Request gate and response headers for every gateway route (spec 0054).

A pure ASGI middleware, so it can refuse an oversized body while it streams in,
before FastAPI parses any JSON.
"""

import hmac
import json
import logging
from collections.abc import Callable
from urllib.parse import urlparse

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from shield_api.settings import Settings

logger = logging.getLogger(__name__)

DEFAULT_BODY_LIMIT = 262_144
TRAIN_BODY_LIMIT = 1_310_720
MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SESSION_COOKIES = ("shield_session=", "shield_player_session=")

BASE_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
)
HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
PRIVATE = (b"cache-control", b"private, no-store")


# The only request headers the gate reads.
GATE_HEADERS = frozenset(
    {
        "x-shield-proxy-secret",
        "x-shield-botid",
        "sec-fetch-site",
        "origin",
        "cookie",
        "content-length",
    }
)


def proxy_secret(settings: Settings) -> str:
    raw = settings.TRUSTED_PROXY_SECRET
    return raw.get_secret_value().strip() if raw else ""


def proxy_secret_matches(settings: Settings, presented: str) -> bool:
    """Whether a request proves the web proxy's shared secret (constant time)."""
    expected = proxy_secret(settings)
    return bool(expected) and hmac.compare_digest(presented.encode(), expected.encode())


def _origin(url: str) -> str:
    parsed = urlparse(url.strip())
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""


class SecurityMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Callable[[], Settings],
        prefix: str,
        botid_paths: frozenset[str],
    ) -> None:
        self.app = app
        self._settings = settings
        self._botid_paths = botid_paths
        self._origins_for: tuple[int, frozenset[str]] = (0, frozenset())
        self._health = f"{prefix}/health"
        self._webhook = f"{prefix}/billing/webhook"
        self._train = f"{prefix}/game/train"
        self._private_prefixes = (
            f"{prefix}/auth/",
            f"{prefix}/game/saves/",
            f"{prefix}/billing/",
        )
        self._private_paths = frozenset(
            {
                f"{prefix}/clearance",
                f"{prefix}/game/progress",
                f"{prefix}/game/leaderboard/me",
            }
        )

    def _allowed_origins(self, settings: Settings) -> frozenset[str]:
        """CORS_ORIGINS plus the WEB_BASE_URL origin, rebuilt only when settings change."""
        key, origins = self._origins_for
        if key != id(settings):
            allowed = {o.rstrip("/") for o in settings.CORS_ORIGINS}
            if web := _origin(settings.WEB_BASE_URL):
                allowed.add(web)
            origins = frozenset(allowed)
            self._origins_for = (id(settings), origins)
        return origins

    def _is_private(self, path: str) -> bool:
        if path == self._webhook:
            return False
        return path in self._private_paths or path.startswith(self._private_prefixes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        settings = self._settings()
        production = settings.APP_ENV == "production"
        method: str = scope["method"]
        path: str = scope["path"]
        headers: dict[str, str] = {}
        for raw_name, raw_value in scope["headers"]:
            name = raw_name.decode("latin-1").lower()
            if name in GATE_HEADERS:
                headers[name] = raw_value.decode("latin-1")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                extra = list(BASE_HEADERS)
                if production:
                    extra.append(HSTS)
                if self._is_private(path):
                    extra.append(PRIVATE)
                names = {name for name, _ in extra}
                kept = [(k, v) for k, v in message.get("headers", []) if k.lower() not in names]
                message["headers"] = kept + extra
            await send(message)

        refusal = self._refusal(settings, production, method, path, headers)
        if refusal is not None:
            await self._reply(send_with_headers, *refusal)
            return

        if method not in MUTATING:
            await self.app(scope, receive, send_with_headers)
            return

        limit = TRAIN_BODY_LIMIT if path == self._train else DEFAULT_BODY_LIMIT
        declared = headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await self._reply(send_with_headers, 413, "Request body too large.")
            return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                await self._reply(send_with_headers, 413, "Request body too large.")
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send_with_headers)

    def _refusal(
        self,
        settings: Settings,
        production: bool,
        method: str,
        path: str,
        headers: dict[str, str],
    ) -> tuple[int, str] | None:
        exempt = (method == "GET" and path == self._health) or (
            method == "POST" and path == self._webhook
        )
        vouched = proxy_secret_matches(settings, headers.get("x-shield-proxy-secret", ""))
        if production and not exempt and not vouched:
            # Only the web proxy may reach the gateway in production.
            return 403, "Request blocked."
        if (
            production
            and method == "POST"
            and path in self._botid_paths
            and headers.get("x-shield-botid") != "pass"
        ):
            # The proxy runs Vercel BotID on these routes and vouches with this header.
            return 403, "Request blocked."
        if method in MUTATING and path != self._webhook:
            site = headers.get("sec-fetch-site")
            origin = headers.get("origin")
            allowed = self._allowed_origins(settings)
            has_session = any(c in headers.get("cookie", "") for c in SESSION_COOKIES)
            if site is not None and site not in ("same-origin", "none"):
                return 403, "Cross-site request blocked."
            # The proxy already required Origin to be its own page, so a request it
            # vouches for may come from any deployment of the site (previews too).
            if origin is not None and not vouched and origin.rstrip("/") not in allowed:
                return 403, "Cross-site request blocked."
            if production and has_session and origin is None and site is None:
                return 403, "Cross-site request blocked."
        return None

    @staticmethod
    async def _reply(send: Send, status: int, detail: str) -> None:
        payload = json.dumps({"detail": detail}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})
