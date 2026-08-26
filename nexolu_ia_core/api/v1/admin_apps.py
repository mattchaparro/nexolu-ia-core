"""CRUD administrativo de apps cliente (`AppRegistration`).

Protegido con `require_platform_access` (NEXOLU_PLATFORM_API_KEY): el mismo
nivel de acceso que ya usa GET /v1/platform/usage para ver datos de TODAS las
apps. Ninguna app integradora conoce esta key.

La api_key en texto plano solo se devuelve en la respuesta de creacion y de
regeneracion -- despues de eso, el Core la trata como un secreto que no
vuelve a mostrar (aunque la guarda cifrada para poder reenviarla al llamar
de vuelta al backend de la app, ver `core/tools/dispatch_client.py`).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexolu_ia_core.core.auth.dependencies import require_platform_access
from nexolu_ia_core.core.auth.repository import AppRegistrationRepository
from nexolu_ia_core.core.memory.db import get_session
from nexolu_ia_core.core.memory.entities import AppRegistration
from nexolu_ia_core.core.schemas import (
    AppRegistrationCreatedOut,
    AppRegistrationIn,
    AppRegistrationOut,
    AppRegistrationPatch,
)

router = APIRouter(
    prefix="/v1/admin/apps",
    tags=["admin"],
    dependencies=[Depends(require_platform_access)],
)


def _mask(api_key: str) -> str:
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:6]}...{api_key[-4:]}"


def _to_out(registration: AppRegistration) -> AppRegistrationOut:
    return AppRegistrationOut(
        id=registration.id,
        app_id=registration.app_id,
        name=registration.name,
        api_key_masked=_mask(registration.api_key),
        is_active=registration.is_active,
        base_url=registration.base_url,
        site_url=registration.site_url,
        site_name=registration.site_name,
        provider=registration.provider,
        model=registration.model,
        has_provider_api_key=bool(registration.provider_api_key),
        provider_preferences=registration.provider_preferences or {},
    )


def _to_created_out(registration: AppRegistration) -> AppRegistrationCreatedOut:
    return AppRegistrationCreatedOut(**_to_out(registration).model_dump(), api_key=registration.api_key)


async def _get_or_404(repo: AppRegistrationRepository, app_id: str) -> AppRegistration:
    registration = await repo.get_by_app_id(app_id)
    if registration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"App '{app_id}' no existe.")
    return registration


@router.get("", response_model=list[AppRegistrationOut])
async def list_apps(session: AsyncSession = Depends(get_session)) -> list[AppRegistrationOut]:
    registrations = await AppRegistrationRepository(session).list_all()
    return [_to_out(r) for r in registrations]


@router.post("", response_model=AppRegistrationCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_app(
    payload: AppRegistrationIn, session: AsyncSession = Depends(get_session)
) -> AppRegistrationCreatedOut:
    repo = AppRegistrationRepository(session)

    if await repo.get_by_app_id(payload.app_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"La app '{payload.app_id}' ya esta registrada."
        )

    registration = await repo.create(**payload.model_dump())
    await session.commit()
    return _to_created_out(registration)


@router.patch("/{app_id}", response_model=AppRegistrationOut)
async def update_app(
    app_id: str, payload: AppRegistrationPatch, session: AsyncSession = Depends(get_session)
) -> AppRegistrationOut:
    repo = AppRegistrationRepository(session)
    registration = await _get_or_404(repo, app_id)

    registration = await repo.update(registration, **payload.model_dump(exclude_unset=True))
    await session.commit()
    return _to_out(registration)


@router.post("/{app_id}/regenerate-key", response_model=AppRegistrationCreatedOut)
async def regenerate_key(app_id: str, session: AsyncSession = Depends(get_session)) -> AppRegistrationCreatedOut:
    repo = AppRegistrationRepository(session)
    registration = await _get_or_404(repo, app_id)

    registration = await repo.regenerate_key(registration)
    await session.commit()
    return _to_created_out(registration)
