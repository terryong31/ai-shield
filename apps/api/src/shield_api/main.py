import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import TypeAdapter

from shield_api.container import Container, build_container
from shield_api.routers import api_router
from shield_api.schemas import ChatEvent
from shield_api.settings import Settings


def _add_stream_schemas(app: FastAPI) -> None:
    """Publish the NDJSON event models, which FastAPI cannot infer from a stream."""
    default_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = default_openapi()
        event_schema = TypeAdapter(ChatEvent).json_schema(
            ref_template="#/components/schemas/{model}"
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components.update(event_schema.pop("$defs", {}))
        components["ChatEvent"] = event_schema
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def create_app(container: Container | None = None, settings: Settings | None = None) -> FastAPI:
    settings = container.settings if container else (settings or Settings())
    logging.basicConfig(level=settings.LOG_LEVEL)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not hasattr(app.state, "container"):
            app.state.container = build_container(settings)
        yield

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        summary="Demo gateway over the AI S.H.I.E.L.D. prompt-injection engine.",
        openapi_url=f"{settings.API_PREFIX}/openapi.json",
        docs_url=f"{settings.API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    if container is not None:
        app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(api_router, prefix=settings.API_PREFIX)
    _add_stream_schemas(app)
    return app


app = create_app()
