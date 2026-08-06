"""Consulta de uso/costo agregado.

El registro de uso ya ocurre dentro de `ChatOrchestrator` (siempre, sin
condicionarlo a ningun plan comercial). Este modulo es el lado de lectura,
con dos audiencias distintas para el mismo dato crudo (`UsageDaily`):

- Una app integradora ve SU propio gasto (opcionalmente por negocio) via
  `summary`/`by_business`/`daily_series` - autenticada con su propia API key,
  nunca ve datos de otra app.
- Nexolu como plataforma ve el gasto de TODAS las apps via `by_app` -
  autenticada aparte (ver `require_platform_access`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from nexolu_ia_core.core.memory.entities import UsageDaily
from nexolu_ia_core.core.memory.repository import ConversationRepository


@dataclass(frozen=True)
class UsageSummary:
    message_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class UsageBreakdown:
    """Un UsageSummary con la clave (business_id o app_id) que lo agrupa."""

    key: str
    summary: UsageSummary


@dataclass(frozen=True)
class UsageDailyPoint:
    date: date
    summary: UsageSummary


def _summary_from_row(row: UsageDaily) -> UsageSummary:
    return UsageSummary(
        message_count=row.message_count,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cost_usd=row.cost_micros / 1_000_000,
    )


def _summary_from_aggregate(message_count: int, input_tokens: int, output_tokens: int, cost_micros: int) -> UsageSummary:
    return UsageSummary(
        message_count=message_count or 0,
        input_tokens=input_tokens or 0,
        output_tokens=output_tokens or 0,
        cost_usd=(cost_micros or 0) / 1_000_000,
    )


class UsageService:
    def __init__(self, repository: ConversationRepository) -> None:
        self._repo = repository

    async def today(self, app_id: str, business_id: str) -> UsageSummary:
        row = await self._repo.usage_today(app_id, business_id)
        return _summary_from_row(row) if row else UsageSummary(0, 0, 0, 0.0)

    async def summary(
        self, *, app_id: str, business_id: str | None, date_from: date, date_to: date
    ) -> UsageSummary:
        """Total del rango para una app (todos sus negocios si business_id es
        None, o uno solo si se filtra)."""
        rows = await self._repo.usage_daily_series(
            app_id=app_id, business_id=business_id, date_from=date_from, date_to=date_to
        )
        return UsageSummary(
            message_count=sum(r.message_count for r in rows),
            input_tokens=sum(r.input_tokens for r in rows),
            output_tokens=sum(r.output_tokens for r in rows),
            cost_usd=sum(r.cost_micros for r in rows) / 1_000_000,
        )

    async def daily_series(
        self, *, app_id: str, business_id: str | None, date_from: date, date_to: date
    ) -> list[UsageDailyPoint]:
        rows = await self._repo.usage_daily_series(
            app_id=app_id, business_id=business_id, date_from=date_from, date_to=date_to
        )
        return [UsageDailyPoint(date=r.date, summary=_summary_from_row(r)) for r in rows]

    async def by_business(self, *, app_id: str, date_from: date, date_to: date) -> list[UsageBreakdown]:
        rows = await self._repo.usage_by_business(app_id=app_id, date_from=date_from, date_to=date_to)
        return [
            UsageBreakdown(key=business_id, summary=_summary_from_aggregate(mc, it, ot, cm))
            for business_id, mc, it, ot, cm in rows
        ]

    async def by_app(self, *, date_from: date, date_to: date) -> list[UsageBreakdown]:
        rows = await self._repo.usage_by_app(date_from=date_from, date_to=date_to)
        return [
            UsageBreakdown(key=app_id, summary=_summary_from_aggregate(mc, it, ot, cm))
            for app_id, mc, it, ot, cm in rows
        ]
