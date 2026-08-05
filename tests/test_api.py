"""Pruebas de los endpoints HTTP, de punta a punta contra la app en memoria
(via ASGI transport, sin bind de socket real)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from nexolu_ia_core.core.memory.db import get_engine, get_sessionmaker, init_models
from nexolu_ia_core.core.memory.repository import ConversationRepository

HEADERS = {"Authorization": "Bearer dev-pos-key"}
CONTEXT = {
    "business_id": "b1",
    "user_id": "u1",
    "is_admin": True,
    "permissions": [],
    "features": [],
    "channel": "web",
}


@pytest.fixture
async def client():
    await init_models()
    from nexolu_ia_core.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await get_engine().dispose()


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_chat_requires_authorization(client):
    response = await client.post(
        "/v1/chat", json={"agent": "cajero", "message": "hola", "context": CONTEXT}
    )
    assert response.status_code == 401


async def test_chat_rejects_unknown_api_key(client):
    response = await client.post(
        "/v1/chat",
        json={"agent": "cajero", "message": "hola", "context": CONTEXT},
        headers={"Authorization": "Bearer no-existe"},
    )
    assert response.status_code == 401


async def test_chat_happy_path_and_history_roundtrip(client):
    response = await client.post(
        "/v1/chat",
        json={"agent": "cajero", "message": "hola, como va todo?", "context": CONTEXT},
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"]
    assert body["text"]

    history = await client.get(
        f"/v1/conversations/{body['conversation_id']}",
        params={"business_id": "b1", "user_id": "u1"},
        headers=HEADERS,
    )
    assert history.status_code == 200
    roles = [m["role"] for m in history.json()["messages"]]
    assert roles == ["user", "assistant"]


async def test_chat_unknown_agent_returns_404(client):
    response = await client.post(
        "/v1/chat",
        json={"agent": "no_existe", "message": "hola", "context": CONTEXT},
        headers=HEADERS,
    )
    assert response.status_code == 404


async def test_draft_confirm_dispatches_to_app_and_marks_confirmed(client, httpx_mock):
    async with get_sessionmaker()() as session:
        repo = ConversationRepository(session)
        conversation = await repo.get_or_create(
            app_id="pos",
            context=_context_obj(),
            agent="cajero",
            conversation_id=None,
            first_text="hola",
        )
        draft = await repo.create_draft(
            conversation_id=conversation.id,
            app_id="pos",
            business_id="b1",
            user_id="u1",
            draft_type="gasto",
            tool_name="crear_gasto",
            payload={"concepto": "Papeleria", "monto": 25000},
            summary="Gasto: Papeleria por $25000",
        )
        await session.commit()
        draft_id = draft.id

    httpx_mock.add_response(url="http://pos.test/api/ai/tools/invoke", json={"data": {"id": 42}})

    response = await client.post(
        f"/v1/drafts/{draft_id}/confirm",
        json={"context": CONTEXT},
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {"status": "confirmed", "data": {"id": 42}}

    dispatched = httpx_mock.get_requests()[0]
    import json as json_module

    dispatched_body = json_module.loads(dispatched.content)
    assert dispatched_body["tool"] == "crear_gasto"
    assert dispatched_body["arguments"] == {"concepto": "Papeleria", "monto": 25000}


async def test_draft_confirm_twice_conflicts(client, httpx_mock):
    async with get_sessionmaker()() as session:
        repo = ConversationRepository(session)
        conversation = await repo.get_or_create(
            app_id="pos", context=_context_obj(), agent="cajero", conversation_id=None, first_text="hola"
        )
        draft = await repo.create_draft(
            conversation_id=conversation.id,
            app_id="pos",
            business_id="b1",
            user_id="u1",
            draft_type="gasto",
            tool_name="crear_gasto",
            payload={"concepto": "Papeleria", "monto": 25000},
            summary="resumen",
        )
        await session.commit()
        draft_id = draft.id

    httpx_mock.add_response(url="http://pos.test/api/ai/tools/invoke", json={"data": {}})

    first = await client.post(f"/v1/drafts/{draft_id}/confirm", json={"context": CONTEXT}, headers=HEADERS)
    assert first.status_code == 200

    second = await client.post(f"/v1/drafts/{draft_id}/confirm", json={"context": CONTEXT}, headers=HEADERS)
    assert second.status_code == 409


async def test_draft_discard(client):
    async with get_sessionmaker()() as session:
        repo = ConversationRepository(session)
        conversation = await repo.get_or_create(
            app_id="pos", context=_context_obj(), agent="cajero", conversation_id=None, first_text="hola"
        )
        draft = await repo.create_draft(
            conversation_id=conversation.id,
            app_id="pos",
            business_id="b1",
            user_id="u1",
            draft_type="gasto",
            tool_name="crear_gasto",
            payload={"concepto": "x", "monto": 1},
            summary="resumen",
        )
        await session.commit()
        draft_id = draft.id

    response = await client.post(f"/v1/drafts/{draft_id}/discard", json={"context": CONTEXT}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"status": "discarded"}


def _context_obj():
    from nexolu_ia_core.core.schemas import TenantContext

    return TenantContext(**CONTEXT)
