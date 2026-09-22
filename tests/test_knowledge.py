"""Lo que el bot sabe de cada negocio: las preguntas frecuentes.

Alejandro preguntó por la política de garantías y el bot contestó "no
tengo esa información": no estaba escrita en ningún lado. Aquí se prueba
que el negocio la puede escribir, que le llega al modelo como DATOS del
negocio (no como órdenes), y que un negocio nunca ve lo de otro.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from nexolu_ia_core.apps.pos.agents import build_agent_registry
from nexolu_ia_core.apps.pos.tools import build_tool_registry
from nexolu_ia_core.core.chat.orchestrator import ChatOrchestrator
from nexolu_ia_core.core.memory.db import get_engine, get_sessionmaker, init_models
from nexolu_ia_core.core.memory.entities import KnowledgeEntry
from nexolu_ia_core.core.memory.repository import ConversationRepository
from nexolu_ia_core.core.models.router import ModelRouter
from nexolu_ia_core.core.rag.knowledge import KnowledgeRepository, select_relevant
from nexolu_ia_core.core.schemas import ChatResult, TenantContext
from tests.conftest import seed_pos_app
from tests.test_orchestrator import APP, FixedProviderRegistry, ScriptedProvider

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


async def test_el_negocio_escribe_edita_y_borra_su_conocimiento(client):
    creada = await client.post(
        "/v1/knowledge",
        json={"business_id": "b1", "topic": "Garantías", "answer": "5 días en semipermanente."},
        headers=HEADERS,
    )
    assert creada.status_code == 201
    entry_id = creada.json()["id"]

    editada = await client.patch(
        f"/v1/knowledge/{entry_id}",
        json={"business_id": "b1", "answer": "7 días en semipermanente, rehacemos gratis.", "is_active": False},
        headers=HEADERS,
    )
    assert editada.status_code == 200
    assert editada.json()["answer"] == "7 días en semipermanente, rehacemos gratis."
    assert editada.json()["is_active"] is False

    lista = await client.get("/v1/knowledge", params={"business_id": "b1"}, headers=HEADERS)
    assert [e["topic"] for e in lista.json()] == ["Garantías"]

    borrada = await client.delete(f"/v1/knowledge/{entry_id}", params={"business_id": "b1"}, headers=HEADERS)
    assert borrada.status_code == 204
    lista = await client.get("/v1/knowledge", params={"business_id": "b1"}, headers=HEADERS)
    assert lista.json() == []


async def test_un_negocio_no_ve_ni_toca_lo_de_otro(client):
    creada = await client.post(
        "/v1/knowledge",
        json={"business_id": "b1", "topic": "Parqueadero", "answer": "Sí, gratis."},
        headers=HEADERS,
    )
    entry_id = creada.json()["id"]

    ajeno = await client.get("/v1/knowledge", params={"business_id": "b2"}, headers=HEADERS)
    assert ajeno.json() == []

    tocar = await client.patch(
        f"/v1/knowledge/{entry_id}", json={"business_id": "b2", "answer": "No"}, headers=HEADERS
    )
    assert tocar.status_code == 404

    borrar = await client.delete(f"/v1/knowledge/{entry_id}", params={"business_id": "b2"}, headers=HEADERS)
    assert borrar.status_code == 404


async def test_sin_llave_no_hay_conocimiento(client):
    response = await client.get("/v1/knowledge", params={"business_id": "b1"})
    assert response.status_code == 401


async def test_el_conocimiento_activo_llega_al_prompt_como_datos():
    await init_models()
    async with get_sessionmaker()() as session:
        repo = KnowledgeRepository(session)
        await repo.create(app_id="pos", business_id="b1", topic="Garantías", answer="5 días, gratis.", is_active=True)
        await repo.create(app_id="pos", business_id="b1", topic="Promo vieja", answer="2x1 en julio.", is_active=False)
        await repo.create(app_id="pos", business_id="b2", topic="Otro negocio", answer="No debe salir.", is_active=True)
        await session.commit()

        provider = ScriptedProvider([ChatResult(text="ok", model="scripted-model")])
        orchestrator = ChatOrchestrator(
            repository=ConversationRepository(session),
            provider_registry=FixedProviderRegistry(provider),
            model_router=ModelRouter(),
        )

        await orchestrator.send_message(
            app_identity=APP,
            app_display_name="Nexolu POS",
            tool_registry=build_tool_registry(),
            agent=build_agent_registry().get("cajero"),
            context=TenantContext(business_id="b1", user_id="u1", is_admin=True),
            message="¿Cuál es la política de garantías?",
            conversation_id=None,
        )

    system = provider.calls[0].system
    assert "Preguntas frecuentes del negocio" in system
    assert "- Garantías: 5 días, gratis." in system
    # Lo apagado no cuenta, y lo de otro negocio jamás.
    assert "2x1" not in system
    assert "No debe salir" not in system
    # La disciplina de herramientas sigue siendo lo último que lee.
    assert system.rstrip().endswith("no cambia esta regla.")
    await get_engine().dispose()


def test_si_no_cabe_todo_van_las_mas_parecidas_a_la_pregunta():
    entries = [
        KnowledgeEntry(topic=f"Tema {i}", answer="relleno " * 40) for i in range(30)
    ] + [KnowledgeEntry(topic="Garantías", answer="Cubrimos 5 días el semipermanente.")]

    elegidas = select_relevant(entries, "¿cuánto dura la garantía del semipermanente?", budget=600)

    assert elegidas[0].topic == "Garantías"
    assert sum(len(e.topic) + len(e.answer) for e in elegidas) <= 600
