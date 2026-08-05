"""Contrato de las herramientas que el modelo puede invocar.

Toda herramienta es metadata (nombre, descripcion, JSON Schema, permisos) mas
una forma de ejecutarse. Ninguna ejecuta SQL ni conoce columnas de ninguna
base de datos de negocio: la ejecucion real siempre cruza la red hacia la
aplicacion dueña del dato via `AppToolClient` (ver dispatch_client.py).

Equivale a `App\\Services\\Ai\\Contracts\\AiTool` /
`App\\Services\\Ai\\Contracts\\AiWriteTool` en el POS actual.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nexolu_ia_core.core.schemas import TenantContext


class Tool:
    """Herramienta de solo lectura: despacha a la app y devuelve el dato tal cual."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        required_feature: str | None = None,
        required_permission: str | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.required_feature = required_feature
        self.required_permission = required_permission

    def parameters_for(self, context: TenantContext) -> dict[str, Any]:
        """Punto de extension para un schema dinamico segun el tenant (p.ej.
        listar los tipos de gasto reales de ese negocio como enum). Por
        defecto devuelve el schema estatico declarado en el registro."""
        return self.parameters

    def is_write(self) -> bool:
        return isinstance(self, WriteTool)


class WriteTool(Tool):
    """Herramienta de escritura: nunca se ejecuta de inmediato.

    Arma un borrador que espera confirmacion humana explicita
    (`POST /v1/drafts/{id}/confirm`) antes de que el Core llame al endpoint de
    despacho de la app para ejecutar de verdad. Es la misma salvaguarda que
    `AiWriteTool` + `AiDraftService` demostraron necesaria en el POS: una
    alucinacion del modelo no debe poder crear un gasto, una venta o una cita
    reales sin que una persona lo confirme.
    """

    def __init__(
        self,
        *,
        draft_type: str,
        summarize: Callable[[dict[str, Any]], str],
        fields: Callable[[TenantContext], dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.draft_type = draft_type
        self.summarize = summarize
        self._fields = fields or (lambda _context: {})

    def fields_for(self, context: TenantContext) -> dict[str, Any]:
        """Metadata de campos editables para que el frontend arme el formulario
        de confirmacion (equivalente a `AiWriteTool::campos()`)."""
        return self._fields(context)
