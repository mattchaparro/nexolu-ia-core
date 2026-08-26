"""Pruebas de los endpoints HTTP de reporte de uso/costo (ver
api/v1/usage.py): scoping por app propia vs plataforma cross-app."""
from __future__ import annotations

from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from nexolu_ia_core.config import get_settings
from nexolu_ia_core.core.memory.db import get_engine, get_sessionmaker, init_models
from nexolu_ia_core.core.memory.repository import ConversationRepository
from tests.conftest import seed_pos_app

HEADERS = {"Authorization": "Bearer dev-pos-key"}


@pytest.fixture
async def client():
    await init_models()
    await seed_pos_app()
    from nexolu_ia_core.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await get_engine().dispose()


async def _seed_usage(*, app_id: str, business_id: str, input_tokens: int, output_tokens: int, cost_micros: int) -> None:
    async with get_sessionmaker()() as session:
        repo = ConversationRepository(session)
        await repo.record_usage(
            app_id=app_id, business_id=business_id, input_tokens=input_tokens, output_tokens=output_tokens,
            cost_micros=cost_micros,
        )
        await session.commit()


async def test_usage_summary_requires_authorization(client):
    response = await client.get("/v1/usage/summary")
    assert response.status_code == 401


async def test_usage_summary_totals_the_callers_own_app_across_businesses(client):
    await _seed_usage(app_id="pos", business_id="b1", input_tokens=100, output_tokens=50, cost_micros=1000)
    await _seed_usage(app_id="pos", business_id="b2", input_tokens=200, output_tokens=80, cost_micros=2000)
    await _seed_usage(app_id="otra_app", business_id="b1", input_tokens=999, output_tokens=999, cost_micros=999_999)

    response = await client.get("/v1/usage/summary", headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["message_count"] == 2
    assert body["summary"]["input_tokens"] == 300
    assert body["summary"]["cost_usd"] == pytest.approx(0.003)

    by_business = {row["key"]: row for row in body["by_business"]}
    assert by_business["b1"]["input_tokens"] == 100
    assert by_business["b2"]["input_tokens"] == 200
    assert "otra_app" not in str(body)


async def test_usage_summary_can_filter_to_one_business(client):
    await _seed_usage(app_id="pos", business_id="b1", input_tokens=100, output_tokens=50, cost_micros=1000)
    await _seed_usage(app_id="pos", business_id="b2", input_tokens=200, output_tokens=80, cost_micros=2000)

    response = await client.get("/v1/usage/summary", params={"business_id": "b1"}, headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["input_tokens"] == 100
    assert body["by_business"] is None


async def test_usage_daily_returns_one_point_per_day(client):
    await _seed_usage(app_id="pos", business_id="b1", input_tokens=10, output_tokens=5, cost_micros=100)

    response = await client.get("/v1/usage/daily", headers=HEADERS)

    assert response.status_code == 200
    days = response.json()["days"]
    assert len(days) == 1
    assert days[0]["date"] == date.today().isoformat()
    assert days[0]["input_tokens"] == 10


async def test_platform_usage_requires_the_platform_key_not_an_app_key(client, monkeypatch):
    monkeypatch.setenv("NEXOLU_PLATFORM_API_KEY", "platform-secret")
    get_settings.cache_clear()

    response = await client.get("/v1/platform/usage", headers=HEADERS)

    assert response.status_code == 401
    get_settings.cache_clear()


async def test_platform_usage_is_disabled_when_not_configured(client):
    response = await client.get("/v1/platform/usage", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 503


async def test_platform_usage_groups_by_app(client, monkeypatch):
    monkeypatch.setenv("NEXOLU_PLATFORM_API_KEY", "platform-secret")
    get_settings.cache_clear()

    await _seed_usage(app_id="pos", business_id="b1", input_tokens=100, output_tokens=0, cost_micros=1000)
    await _seed_usage(app_id="spa", business_id="b7", input_tokens=50, output_tokens=0, cost_micros=500)

    response = await client.get(
        "/v1/platform/usage", headers={"Authorization": "Bearer platform-secret"}
    )

    assert response.status_code == 200
    breakdown = {row["key"]: row for row in response.json()["breakdown"]}
    assert breakdown["pos"]["input_tokens"] == 100
    assert breakdown["spa"]["input_tokens"] == 50
    get_settings.cache_clear()


async def test_platform_usage_can_drill_into_one_apps_businesses(client, monkeypatch):
    monkeypatch.setenv("NEXOLU_PLATFORM_API_KEY", "platform-secret")
    get_settings.cache_clear()

    await _seed_usage(app_id="pos", business_id="b1", input_tokens=100, output_tokens=0, cost_micros=1000)
    await _seed_usage(app_id="pos", business_id="b2", input_tokens=40, output_tokens=0, cost_micros=400)

    response = await client.get(
        "/v1/platform/usage", params={"app_id": "pos"}, headers={"Authorization": "Bearer platform-secret"}
    )

    assert response.status_code == 200
    breakdown = {row["key"]: row for row in response.json()["breakdown"]}
    assert breakdown["b1"]["input_tokens"] == 100
    assert breakdown["b2"]["input_tokens"] == 40
    get_settings.cache_clear()
