"""Consulta de uso/costo agregado.

El registro de uso ya ocurre dentro de `ChatOrchestrator` (siempre, sin
condicionarlo a ningun plan comercial). Este modulo es el lado de lectura:
lo que un endpoint de reporte, o el propio dashboard de una app, usaria para
mostrar cuanto ha consumido un tenant.
"""
from __future__ import annotations

from dataclasses import dataclass

from nexolu_ia_core.core.memory.repository import ConversationRepository


@dataclass(frozen=True)
class UsageSummary:
    message_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class UsageService:
    def __init__(self, repository: ConversationRepository) -> None:
        self._repo = repository

    async def today(self, app_id: str, business_id: str) -> UsageSummary:
        row = await self._repo.usage_today(app_id, business_id)
        if row is None:
            return UsageSummary(message_count=0, input_tokens=0, output_tokens=0, cost_usd=0.0)

        return UsageSummary(
            message_count=row.message_count,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cost_usd=row.cost_micros / 1_000_000,
        )
