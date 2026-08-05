"""Punto de entrada del servicio: `uvicorn nexolu_ia_core.main:app`."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from nexolu_ia_core.api.v1 import chat, conversations, drafts, health
from nexolu_ia_core.config import get_settings
from nexolu_ia_core.core.memory.db import init_models
from nexolu_ia_core.core.telemetry.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    # Autocrear tablas solo tiene sentido en SQLite de desarrollo. En
    # produccion (Postgres) el esquema se maneja con `alembic upgrade head`,
    # corrido como parte del despliegue, no al arrancar el proceso.
    if settings.database_url.startswith("sqlite"):
        await init_models()

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Nexolu IA Core",
        description="Plataforma de inteligencia artificial reutilizable para todo el ecosistema Nexolu.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    app.include_router(drafts.router)

    return app


app = create_app()
