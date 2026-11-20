import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shield_api.container import Container, build_container
from shield_api.routers import api_router
from shield_api.services.scores import RedisCachedScoreStore
from shield_api.settings import Settings


def create_app(container: Container | None = None, settings: Settings | None = None) -> FastAPI:
    settings = container.settings if container else (settings or Settings())
    logging.basicConfig(level=settings.LOG_LEVEL)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not hasattr(app.state, "container"):
            app.state.container = build_container(settings)
        warmup_task: asyncio.Task[None] | None = None
        if isinstance(app.state.container.scores, RedisCachedScoreStore):
            warmup_task = asyncio.create_task(app.state.container.scores.warm_cache())
        try:
            yield
        finally:
            if warmup_task is not None and not warmup_task.done():
                warmup_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await warmup_task

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        # PUT saves boards (spec 0023, API-SAVE-007).
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(api_router, prefix=settings.API_PREFIX)
    return app


app = create_app()
