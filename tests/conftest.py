"""Fixtures compartidas.

`Settings`, el engine de BD, el registro de proveedores y el Fernet de
`core/security/crypto.py` estan cacheados con `lru_cache` (a proposito: son
singletons de proceso en produccion). Para que cada test corra aislado con
su propio `DATABASE_URL`, este fixture limpia esos caches antes y despues de
cada test.
"""
from __future__ import annotations

import pytest

# Clave Fernet fija y valida (no una key real) - basta con que sea estable
# durante toda la suite; cada test usa su propia BD (`DATABASE_URL` distinto)
# asi que compartir la master key entre tests no filtra nada entre ellos.
TEST_MASTER_KEY = "wLQAPfdYOhoEWkiIv14sWmQEg-8O8Fknr6OFW-9Nrw4="

# Api key en claro que la mayoria de tests HTTP usa para autenticarse como
# la app "pos" -- ver `seed_pos_app()`.
POS_API_KEY = "dev-pos-key"


@pytest.fixture(autouse=True)
def app_env(tmp_path, monkeypatch):
    from nexolu_ia_core.config import Settings

    # La suite NO lee el .env del desarrollador.
    #
    # `Settings` declara `env_file=".env"`, asi que pydantic lo carga aunque
    # la variable no este exportada. Eso hace que una prueba cambie de
    # resultado en cuanto alguien configura el servicio para trabajar en
    # local: "esta apagado si no hay llave de plataforma" empieza a fallar
    # porque ahora SI hay llave, sin que nadie haya tocado el codigo.
    monkeypatch.setitem(Settings.model_config, "env_file", None)

    # Y tampoco hereda lo que este exportado en la terminal: las pruebas que
    # necesitan llave de plataforma la ponen ellas con `monkeypatch.setenv`.
    monkeypatch.delenv("NEXOLU_PLATFORM_API_KEY", raising=False)

    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("IA_CORE_MASTER_KEY", TEST_MASTER_KEY)
    monkeypatch.setenv("DEFAULT_PROVIDER", "null")

    _clear_caches()
    yield
    _clear_caches()


def _clear_caches() -> None:
    import nexolu_ia_core.core.tools.remote_catalog as remote_catalog_module
    from nexolu_ia_core.config import get_settings
    from nexolu_ia_core.core.memory.db import get_engine, get_sessionmaker
    from nexolu_ia_core.core.security.crypto import _fernet
    from nexolu_ia_core.providers.registry import get_provider_registry

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_provider_registry.cache_clear()
    _fernet.cache_clear()
    remote_catalog_module._instance = None


async def seed_pos_app(
    *, app_id: str = "pos", api_key: str = POS_API_KEY, base_url: str = "http://pos.test", **fields
) -> None:
    """Inserta la app `pos` de prueba en la BD -- reemplaza el viejo
    `NEXOLU_APPS_JSON` de env var. Se llama DESPUES de `init_models()`
    (necesita que la tabla `app_registrations` ya exista)."""
    from nexolu_ia_core.core.auth.repository import AppRegistrationRepository
    from nexolu_ia_core.core.memory.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        repo = AppRegistrationRepository(session)
        await repo.create(app_id=app_id, api_key=api_key, base_url=base_url, name="Nexolu POS", **fields)
        await session.commit()
