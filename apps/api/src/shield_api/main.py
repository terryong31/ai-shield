import hmac
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shield_api.container import Container, build_container
from shield_api.routers import api_router
from shield_api.settings import Settings


def create_app(container: Container | None = None, settings: Settings | None = None) -> FastAPI:
    settings = container.settings if container else (settings or Settings())
    logging.basicConfig(level=settings.LOG_LEVEL)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not hasattr(app.state, "container"):
            app.state.container = build_container(settings)
        try:
            yield
        finally:
            await app.state.container.train_worker.aclose()

    # Swagger UI and the schema route only in development; ReDoc never (API-DOCS-001).
    # app.openapi() still works with the routes off, so `mise run contract` is unaffected.
    is_dev = settings.APP_ENV == "development"
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        summary="Demo gateway over the AI S.H.I.E.L.D. prompt-injection engine.",
        openapi_url=f"{settings.API_PREFIX}/openapi.json" if is_dev else None,
        docs_url=f"{settings.API_PREFIX}/docs" if is_dev else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    if container is not None:
        app.state.container = container

    botid_paths = frozenset(
        {
            f"{settings.API_PREFIX}/auth/anonymous",
            f"{settings.API_PREFIX}/auth/register",
            f"{settings.API_PREFIX}/auth/login",
            f"{settings.API_PREFIX}/auth/recover",
            f"{settings.API_PREFIX}/auth/resend-confirmation",
            f"{settings.API_PREFIX}/auth/confirm",
            f"{settings.API_PREFIX}/auth/reset-password",
            f"{settings.API_PREFIX}/game/run",
            f"{settings.API_PREFIX}/game/train",
        }
    )
    auth_prefix = f"{settings.API_PREFIX}/auth/"
    clearance_path = f"{settings.API_PREFIX}/clearance"
    proxy_secret = (
        settings.TRUSTED_PROXY_SECRET.get_secret_value().strip()
        if settings.TRUSTED_PROXY_SECRET
        else ""
    )
    if not is_dev and not proxy_secret:
        logging.getLogger(__name__).error(
            "APP_ENV is production and TRUSTED_PROXY_SECRET is unset; "
            "blocking BotID-protected routes."
        )
    signing_secret = (
        settings.MODEL_SIGNING_KEY.get_secret_value().strip() if settings.MODEL_SIGNING_KEY else ""
    )
    if not is_dev and not signing_secret:
        logging.getLogger(__name__).error(
            "APP_ENV is production and MODEL_SIGNING_KEY is unset; /game/train is disabled."
        )

    train_path = f"{settings.API_PREFIX}/game/train"
    max_train_body = 1_310_720

    @app.middleware("http")
    async def verify_botid(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        active_container = getattr(app.state, "container", None)
        active_settings = active_container.settings if active_container is not None else settings
        if request.method == "POST" and request.url.path == train_path:
            raw_len = request.headers.get("content-length")
            if raw_len is not None:
                try:
                    if int(raw_len) > max_train_body:
                        return JSONResponse(
                            {"detail": "Training upload exceeds the maximum size."},
                            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        )
                except ValueError:
                    pass
            if len(await request.body()) > max_train_body:
                return JSONResponse(
                    {"detail": "Training upload exceeds the maximum size."},
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                )
        if (
            active_settings.APP_ENV == "production"
            and request.method == "POST"
            and request.url.path in botid_paths
        ):
            expected = (
                active_settings.TRUSTED_PROXY_SECRET.get_secret_value().strip()
                if active_settings.TRUSTED_PROXY_SECRET
                else ""
            )
            presented = request.headers.get("x-shield-proxy-secret", "")
            botid = request.headers.get("x-shield-botid", "")
            if not expected or not hmac.compare_digest(presented, expected) or botid != "pass":
                return JSONResponse(
                    {"detail": "Request blocked."}, status_code=status.HTTP_403_FORBIDDEN
                )
        response = await call_next(request)
        if request.url.path.startswith(auth_prefix) or request.url.path == clearance_path:
            response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        # PUT saves boards (spec 0023, API-SAVE-007).
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(api_router, prefix=settings.API_PREFIX)
    return app


app = create_app()
