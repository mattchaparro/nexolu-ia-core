"""Punto de entrada del servicio: `uvicorn nexolu_ia_core.main:app`."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles

from nexolu_ia_core.api.v1 import (
    admin_apps,
    admin_drafts,
    admin_tool_logs,
    chat,
    completions,
    conversations,
    drafts,
    health,
    knowledge,
    usage,
)
from nexolu_ia_core.config import get_settings
from nexolu_ia_core.core.memory.db import init_models
from nexolu_ia_core.core.telemetry.logging import configure_logging

# docs/openapi/ vive en la raiz del repo, no dentro del paquete instalable.
_OPENAPI_DIR = Path(__file__).resolve().parent.parent / "docs" / "openapi"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    # Autocrear tablas solo tiene sentido en SQLite de desarrollo. En
    # produccion (MySQL) el esquema se maneja con `alembic upgrade head`,
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
    app.include_router(completions.router)
    app.include_router(conversations.router)
    app.include_router(drafts.router)
    app.include_router(knowledge.router)
    app.include_router(usage.router)
    app.include_router(admin_apps.router)
    app.include_router(admin_tool_logs.router)
    app.include_router(admin_drafts.router)

    # La API que el Core EXPONE ya tiene Swagger autogenerado por FastAPI en
    # /docs. Esto es lo complementario: el contrato que una app cliente debe
    # IMPLEMENTAR (POST /api/ai/tools/invoke, GET /api/ai/tools/catalog) no
    # es parte de esta app, asi que no puede salir del autogenerado - se sirve
    # aparte, desde docs/openapi/app-contract.json (ver docs/APP_INTEGRATION.md).
    if _OPENAPI_DIR.is_dir():
        app.mount("/static/openapi", StaticFiles(directory=str(_OPENAPI_DIR)), name="openapi-static")

        @app.get("/docs/app-contract", include_in_schema=False)
        async def app_contract_docs():
            return get_swagger_ui_html(
                openapi_url="/static/openapi/app-contract.json",
                title="Nexolu IA Core - Contrato de integracion de apps",
            )

    return app


app = create_app()
