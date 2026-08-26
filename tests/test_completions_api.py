"""Pruebas de POST /v1/completions: redaccion de una sola pasada sin
conversacion ni herramientas (ver api/v1/completions.py)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from nexolu_ia_core.core.memory.db import get_engine, init_models
from tests.conftest import seed_pos_app

HEADERS = {"Authorization": "Bearer dev-pos-key"}
CONTEXT = {
    "business_id": "b1",
    "user_id": "u1",
    "is_admin": True,
    "permissions": [],
    "features": ["expenses"],
    "channel": "web",
}


@pytest.fixture
async def client():
    await init_models()
    await seed_pos_app()
    from nexolu_ia_core.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await get_engine().dispose()


async def test_completions_requires_authorization(client):
    response = await client.post(
        "/v1/completions", json={"system": "Eres breve.", "user": "Ventas: $100.000.", "context": CONTEXT}
    )
    assert response.status_code == 401


async def test_completions_returns_provider_text_without_a_conversation(client):
    response = await client.post(
        "/v1/completions",
        json={"system": "Eres breve.", "user": "Ventas hoy: $100.000, 15% mas que ayer.", "context": CONTEXT},
        headers=HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert "Ventas hoy: $100.000" in body["text"]
    assert body["model"] == "null"
    assert "conversation_id" not in body


async def test_completions_records_usage_for_the_calling_business(client):
    await client.post(
        "/v1/completions",
        json={"system": "Eres breve.", "user": "hola", "context": CONTEXT},
        headers=HEADERS,
    )

    usage = await client.get("/v1/usage/summary", params={"business_id": "b1"}, headers=HEADERS)

    assert usage.status_code == 200
    assert usage.json()["summary"]["message_count"] == 1
