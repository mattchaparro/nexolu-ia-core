"""Pruebas de /v1/admin/apps: CRUD de AppRegistration, protegido con la API
key de plataforma (ver core/auth/dependencies.py::require_platform_access)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from nexolu_ia_core.core.memory.db import get_engine, init_models

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


async def test_list_apps_requires_platform_key(client):
    response = await client.get("/v1/admin/apps")
    assert response.status_code == 401


async def test_list_apps_rejects_a_wrong_platform_key(client):
    response = await client.get("/v1/admin/apps", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


async def test_create_returns_the_api_key_once_and_list_masks_it(client):
    create = await client.post(
        "/v1/admin/apps",
        json={"app_id": "spa", "name": "Nexolu Spa", "base_url": "http://spa.test"},
        headers=PLATFORM_HEADERS,
    )
    assert create.status_code == 201
    body = create.json()
    assert body["app_id"] == "spa"
    assert body["api_key"]
    plain_key = body["api_key"]

    listing = await client.get("/v1/admin/apps", headers=PLATFORM_HEADERS)
    assert listing.status_code == 200
    [entry] = listing.json()
    assert "api_key" not in entry
    assert plain_key not in entry["api_key_masked"]
    assert entry["api_key_masked"].endswith(plain_key[-4:])


async def test_create_duplicate_app_id_conflicts(client):
    payload = {"app_id": "spa", "base_url": "http://spa.test"}
    first = await client.post("/v1/admin/apps", json=payload, headers=PLATFORM_HEADERS)
    assert first.status_code == 201

    second = await client.post("/v1/admin/apps", json=payload, headers=PLATFORM_HEADERS)
    assert second.status_code == 409


async def test_patch_updates_fields_without_touching_the_api_key(client):
    create = await client.post(
        "/v1/admin/apps", json={"app_id": "spa", "base_url": "http://spa.test"}, headers=PLATFORM_HEADERS
    )
    original_masked = create.json()["api_key_masked"]

    patched = await client.patch(
        "/v1/admin/apps/spa",
        json={
            "site_url": "https://spa.nexolu.co",
            "site_name": "Nexolu Spa",
            "is_active": False,
            "provider_preferences": {"order": ["Anthropic"]},
        },
        headers=PLATFORM_HEADERS,
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["site_url"] == "https://spa.nexolu.co"
    assert body["site_name"] == "Nexolu Spa"
    assert body["is_active"] is False
    assert body["provider_preferences"] == {"order": ["Anthropic"]}
    assert body["api_key_masked"] == original_masked


async def test_patch_unknown_app_returns_404(client):
    response = await client.patch("/v1/admin/apps/no-existe", json={"name": "x"}, headers=PLATFORM_HEADERS)
    assert response.status_code == 404


async def test_patch_sets_and_clears_the_budget_limit(client):
    await client.post(
        "/v1/admin/apps", json={"app_id": "spa", "base_url": "http://spa.test"}, headers=PLATFORM_HEADERS
    )

    with_budget = await client.patch(
        "/v1/admin/apps/spa", json={"budget_limit_usd": 50.5}, headers=PLATFORM_HEADERS
    )
    assert with_budget.status_code == 200
    assert with_budget.json()["budget_limit_usd"] == 50.5

    cleared = await client.patch(
        "/v1/admin/apps/spa", json={"budget_limit_usd": None}, headers=PLATFORM_HEADERS
    )
    assert cleared.status_code == 200
    assert cleared.json()["budget_limit_usd"] is None


async def test_refresh_tool_catalog_invalidates_the_cache(client):
    await client.post(
        "/v1/admin/apps", json={"app_id": "spa", "base_url": "http://spa.test"}, headers=PLATFORM_HEADERS
    )

    from nexolu_ia_core.core.tools.remote_catalog import get_remote_tool_catalog

    get_remote_tool_catalog()._cache["spa"] = (0.0, {"herramienta": {"required_permission": "x"}})

    response = await client.post("/v1/admin/apps/spa/tool-catalog/refresh", headers=PLATFORM_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"invalidated": True}
    assert "spa" not in get_remote_tool_catalog()._cache


async def test_refresh_tool_catalog_unknown_app_returns_404(client):
    response = await client.post("/v1/admin/apps/no-existe/tool-catalog/refresh", headers=PLATFORM_HEADERS)
    assert response.status_code == 404


async def test_regenerate_key_issues_a_new_key_and_invalidates_the_old_one(client):
    create = await client.post(
        "/v1/admin/apps", json={"app_id": "spa", "base_url": "http://spa.test"}, headers=PLATFORM_HEADERS
    )
    old_key = create.json()["api_key"]

    regenerated = await client.post("/v1/admin/apps/spa/regenerate-key", headers=PLATFORM_HEADERS)
    assert regenerated.status_code == 200
    new_key = regenerated.json()["api_key"]
    assert new_key != old_key

    rejected = await client.post(
        "/v1/chat",
        json={"agent": "x", "message": "hola", "context": {"user_id": "u1"}},
        headers={"Authorization": f"Bearer {old_key}"},
    )
    assert rejected.status_code == 401
