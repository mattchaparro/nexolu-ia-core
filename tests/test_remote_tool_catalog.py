from __future__ import annotations

import httpx

from nexolu_ia_core.core.auth.apps import AppIdentity
from nexolu_ia_core.core.tools.base import Tool
from nexolu_ia_core.core.tools.registry import ToolRegistry
from nexolu_ia_core.core.tools.remote_catalog import RemoteToolCatalog

APP = AppIdentity(app_id="pos", api_key="dev-pos-key", base_url="http://pos.test", name="Nexolu POS")


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="estado_caja",
            description="d",
            parameters={"type": "object", "properties": {}},
            required_permission="cash.view",
        )
    )
    return registry


async def test_sync_overrides_required_permission_and_feature_from_the_catalog(httpx_mock):
    httpx_mock.add_response(
        url="http://pos.test/api/ai/tools/catalog",
        json={"tools": {"estado_caja": {"required_permission": "cash_shift.manage", "required_feature": "cash_closing"}}},
    )
    registry = build_registry()
    catalog = RemoteToolCatalog(ttl_seconds=86400)

    await catalog.sync(registry, APP)

    tool = registry.all()["estado_caja"]
    assert tool.required_permission == "cash_shift.manage"
    assert tool.required_feature == "cash_closing"


async def test_sync_keeps_the_hardcoded_default_when_the_app_is_unreachable(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("no route to host"))
    registry = build_registry()
    catalog = RemoteToolCatalog(ttl_seconds=86400)

    await catalog.sync(registry, APP)

    tool = registry.all()["estado_caja"]
    assert tool.required_permission == "cash.view"


async def test_sync_does_not_refetch_within_the_ttl(httpx_mock):
    httpx_mock.add_response(
        url="http://pos.test/api/ai/tools/catalog",
        json={"tools": {"estado_caja": {"required_permission": "cash_shift.manage", "required_feature": None}}},
    )
    catalog = RemoteToolCatalog(ttl_seconds=86400)

    await catalog.sync(build_registry(), APP)
    await catalog.sync(build_registry(), APP)  # segunda llamada: no debe pegarle de nuevo a la red

    assert len(httpx_mock.get_requests()) == 1


async def test_sync_falls_back_to_the_stale_cache_when_a_later_fetch_fails(httpx_mock):
    catalog = RemoteToolCatalog(ttl_seconds=0)  # TTL 0: siempre intenta refrescar

    httpx_mock.add_response(
        url="http://pos.test/api/ai/tools/catalog",
        json={"tools": {"estado_caja": {"required_permission": "cash_shift.manage", "required_feature": None}}},
    )
    await catalog.sync(build_registry(), APP)

    httpx_mock.add_exception(httpx.ConnectError("no route to host"))
    registry_two = build_registry()
    await catalog.sync(registry_two, APP)

    assert registry_two.all()["estado_caja"].required_permission == "cash_shift.manage"


async def test_sync_ignores_tool_names_the_catalog_does_not_mention(httpx_mock):
    httpx_mock.add_response(url="http://pos.test/api/ai/tools/catalog", json={"tools": {"otra_herramienta": {}}})
    registry = build_registry()
    catalog = RemoteToolCatalog(ttl_seconds=86400)

    await catalog.sync(registry, APP)

    assert registry.all()["estado_caja"].required_permission == "cash.view"
