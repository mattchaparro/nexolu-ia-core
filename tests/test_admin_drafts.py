"""Pruebas de /v1/admin/drafts: auditoria y purga forzada de borradores,
protegido con la API key de plataforma."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from nexolu_ia_core.core.memory.db import get_engine, get_sessionmaker, init_models
from nexolu_ia_core.core.memory.repository import ConversationRepository

PLATFORM_HEADERS = {"Authorization": "Bearer plat-secret"}


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("NEXOLU_PLATFORM_API_KEY", "plat-secret")
    await init_models()
    from nexolu_ia_core.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await get_engine().dispose()


async def _seed_draft(*, status: str = "pending", app_id: str = "pos") -> str:
    async with get_sessionmaker()() as session:
        repo = ConversationRepository(session)
        draft = await repo.create_draft(
            conversation_id="conv1",
            app_id=app_id,
            business_id="b1",
            user_id="u1",
            draft_type="expense",
            tool_name="crear_gasto",
            payload={"monto": 1000},
            summary="Gasto de 1000",
        )
        draft.status = status
        await session.commit()
        return draft.id


async def test_list_requires_platform_key(client):
    response = await client.get("/v1/admin/drafts")
    assert response.status_code == 401


async def test_list_filters_by_app_and_status(client):
    await _seed_draft(status="pending", app_id="pos")
    await _seed_draft(status="discarded", app_id="pos")
    await _seed_draft(status="pending", app_id="otra_app")

    response = await client.get(
        "/v1/admin/drafts", params={"app_id": "pos", "status": "pending"}, headers=PLATFORM_HEADERS
    )

    assert response.status_code == 200
    [entry] = response.json()
    assert entry["app_id"] == "pos"
    assert entry["status"] == "pending"


async def test_purge_discards_a_pending_draft_without_the_apps_own_key(client):
    draft_id = await _seed_draft(status="pending")

    response = await client.post(f"/v1/admin/drafts/{draft_id}/purge", headers=PLATFORM_HEADERS)

    assert response.status_code == 200
    assert response.json()["status"] == "discarded"


async def test_purge_already_discarded_draft_conflicts(client):
    draft_id = await _seed_draft(status="discarded")
    response = await client.post(f"/v1/admin/drafts/{draft_id}/purge", headers=PLATFORM_HEADERS)
    assert response.status_code == 409


async def test_purge_unknown_draft_returns_404(client):
    response = await client.post("/v1/admin/drafts/no-existe/purge", headers=PLATFORM_HEADERS)
    assert response.status_code == 404
