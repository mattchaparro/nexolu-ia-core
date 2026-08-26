"""Pruebas de /v1/admin/tool-logs: listado y reintento manual de invocaciones
de herramientas fallidas, protegido con la API key de plataforma."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from nexolu_ia_core.core.memory.db import get_engine, get_sessionmaker, init_models
from nexolu_ia_core.core.memory.repository import ConversationRepository
from tests.conftest import seed_pos_app

PLATFORM_HEADERS = {"Authorization": "Bearer plat-secret"}


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("NEXOLU_PLATFORM_API_KEY", "plat-secret")
    await init_models()
    await seed_pos_app()
    from nexolu_ia_core.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await get_engine().dispose()


async def _seed_log(*, status: str, context: dict | None, app_id: str = "pos") -> int:
    async with get_sessionmaker()() as session:
        repo = ConversationRepository(session)
        log = await repo.log_tool_invocation(
            conversation_id="conv1",
            app_id=app_id,
            business_id="b1",
            tool_name="estado_caja",
            arguments={},
            status=status,
            result_summary="boom" if status == "error" else "ok",
            context=context,
        )
        await session.commit()
        return log.id


async def test_list_requires_platform_key(client):
    response = await client.get("/v1/admin/tool-logs")
    assert response.status_code == 401


async def test_list_filters_by_app_and_status(client):
    await _seed_log(status="error", context={"user_id": "u1"}, app_id="pos")
    await _seed_log(status="ok", context={"user_id": "u1"}, app_id="pos")
    await _seed_log(status="error", context={"user_id": "u1"}, app_id="otra_app")

    response = await client.get(
        "/v1/admin/tool-logs", params={"app_id": "pos", "status": "error"}, headers=PLATFORM_HEADERS
    )

    assert response.status_code == 200
    [entry] = response.json()
    assert entry["app_id"] == "pos"
    assert entry["status"] == "error"


async def test_retry_replays_the_dispatch_and_creates_a_new_ok_log(client, httpx_mock):
    log_id = await _seed_log(status="error", context={"user_id": "u1", "business_id": "b1"})

    httpx_mock.add_response(
        url="http://pos.test/api/ai/tools/invoke", json={"data": {"abierta": True}}
    )

    response = await client.post(f"/v1/admin/tool-logs/{log_id}/retry", headers=PLATFORM_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] != log_id
    assert body["status"] == "ok"
    assert body["tool_name"] == "estado_caja"

    listing = await client.get("/v1/admin/tool-logs", headers=PLATFORM_HEADERS)
    assert len(listing.json()) == 2


async def test_retry_records_a_new_failure_when_dispatch_fails_again(client, httpx_mock):
    log_id = await _seed_log(status="error", context={"user_id": "u1", "business_id": "b1"})
    httpx_mock.add_response(url="http://pos.test/api/ai/tools/invoke", status_code=500)

    response = await client.post(f"/v1/admin/tool-logs/{log_id}/retry", headers=PLATFORM_HEADERS)

    assert response.status_code == 200
    assert response.json()["status"] == "error"


async def test_retry_on_already_ok_log_conflicts(client):
    log_id = await _seed_log(status="ok", context={"user_id": "u1"})
    response = await client.post(f"/v1/admin/tool-logs/{log_id}/retry", headers=PLATFORM_HEADERS)
    assert response.status_code == 409


async def test_retry_without_saved_context_conflicts(client):
    log_id = await _seed_log(status="error", context=None)
    response = await client.post(f"/v1/admin/tool-logs/{log_id}/retry", headers=PLATFORM_HEADERS)
    assert response.status_code == 409


async def test_retry_unknown_log_returns_404(client):
    response = await client.post("/v1/admin/tool-logs/999999/retry", headers=PLATFORM_HEADERS)
    assert response.status_code == 404
