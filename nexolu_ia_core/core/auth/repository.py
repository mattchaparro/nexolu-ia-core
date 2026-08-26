"""Acceso a datos de `AppRegistration` (identidad de apps cliente).

Separado de `ConversationRepository` (core/memory/repository.py) a proposito:
esa clase es sobre datos de chat/uso, esta es sobre administracion/identidad
de apps -- ciclos de vida y consumidores distintos (el admin de plataforma
contra esta, el orquestador de chat contra la otra).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexolu_ia_core.core.memory.entities import AppRegistration
from nexolu_ia_core.core.security.api_keys import generate_api_key, hash_api_key


class AppRegistrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[AppRegistration]:
        stmt = select(AppRegistration).order_by(AppRegistration.app_id)
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_by_app_id(self, app_id: str) -> AppRegistration | None:
        stmt = select(AppRegistration).where(AppRegistration.app_id == app_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_active_by_api_key_hash(self, api_key_hash: str) -> AppRegistration | None:
        stmt = select(AppRegistration).where(
            AppRegistration.api_key_hash == api_key_hash,
            AppRegistration.is_active.is_(True),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(self, **fields) -> AppRegistration:
        registration = AppRegistration(**fields)
        self._session.add(registration)
        await self._session.flush()
        return registration

    async def update(self, registration: AppRegistration, **fields) -> AppRegistration:
        """Aplica `fields` tal cual (el caller ya filtro lo que no vino en el
        patch, ver `AppRegistrationPatch.model_dump(exclude_unset=True)`) --
        asi un PATCH SI puede limpiar un campo nullable a `None` a proposito."""
        for key, value in fields.items():
            setattr(registration, key, value)
        await self._session.flush()
        return registration

    async def regenerate_key(self, registration: AppRegistration) -> AppRegistration:
        new_key = generate_api_key()
        registration.api_key = new_key
        registration.api_key_hash = hash_api_key(new_key)
        await self._session.flush()
        return registration
