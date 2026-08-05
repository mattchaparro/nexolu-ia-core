"""Fixtures compartidas.

`Settings`, el engine de BD y el registro de proveedores estan cacheados con
`lru_cache` (a proposito: son singletons de proceso en produccion). Para que
cada test corra aislado con su propio `DATABASE_URL` y su propio registro de
apps, este fixture limpia esos caches antes y despues de cada test.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def app_env(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv(
        "NEXOLU_APPS_JSON",
        json.dumps({"pos": {"api_key": "dev-pos-key", "base_url": "http://pos.test", "name": "Nexolu POS"}}),
    )
    monkeypatch.setenv("DEFAULT_PROVIDER", "null")

    _clear_caches()
    yield
    _clear_caches()


def _clear_caches() -> None:
    import nexolu_ia_core.core.auth.apps as apps_module
    from nexolu_ia_core.config import get_settings
    from nexolu_ia_core.core.memory.db import get_engine, get_sessionmaker
    from nexolu_ia_core.providers.registry import get_provider_registry

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_provider_registry.cache_clear()
    apps_module._registry = None
