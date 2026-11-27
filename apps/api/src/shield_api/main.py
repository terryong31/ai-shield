import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shield_api.container import Container, build_container
from shield_api.routers import api_router
from shield_api.security import SecurityMiddleware, proxy_secret
from shield_api.settings import Settings
from shield_engine.game import RETIRED_LEVEL_IDS


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

    @app.exception_handler(RequestValidationError)
    async def retired_level_is_not_found(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # A level that spec 0051 removed is gone, not malformed (API-LADDER-001).
        for error in exc.errors():
            loc = error.get("loc", ())
            if "level_id" in loc and error.get("input") in RETIRED_LEVEL_IDS:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={"detail": "This level was removed from the campaign."},
                )
        # Never echo what was sent: it can be a password or a token (spec 0054).
        cleaned = [
            {key: value for key, value in error.items() if key not in ("input", "ctx", "url")}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": jsonable_encoder(cleaned)},
        )

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
            f"{settings.API_PREFIX}/clearance",
        }
    )
    if not is_dev and not proxy_secret(settings):
        logging.getLogger(__name__).error(
            "APP_ENV is production and TRUSTED_PROXY_SECRET is unset; every route but "
            "health and the Stripe webhook answers 403."
        )
    signing_secret = (
        settings.MODEL_SIGNING_KEY.get_secret_value().strip() if settings.MODEL_SIGNING_KEY else ""
    )
    if not is_dev and not signing_secret:
        logging.getLogger(__name__).error(
            "APP_ENV is production and MODEL_SIGNING_KEY is unset; /game/train is disabled."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        # PUT saves boards (spec 0023, API-SAVE-007).
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    def active_settings() -> Settings:
        active_container = getattr(app.state, "container", None)
        return active_container.settings if active_container is not None else settings

    # Outermost: the proxy secret, BotID, cross-site checks, body limits and headers (spec 0054).
    app.add_middleware(
        SecurityMiddleware,
        settings=active_settings,
        prefix=settings.API_PREFIX,
        botid_paths=botid_paths,
    )
    app.include_router(api_router, prefix=settings.API_PREFIX)
    return app


app = create_app()
