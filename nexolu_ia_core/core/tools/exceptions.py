from __future__ import annotations

from typing import Any


class ToolInputException(Exception):
    """Argumentos invalidos para una herramienta. Se le devuelve al modelo
    como texto para que corrija y reintente, nunca rompe la conversacion.

    `candidates`, si viene, es una lista de opciones estructuradas (p.ej.
    coincidencias de nombre de cliente) para que el canal pueda ofrecer
    botones/una lista real en vez de obligar a retipear.
    """

    def __init__(self, message: str, candidates: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.candidates = candidates


class ToolNotAllowedException(Exception):
    """La herramienta no existe o no esta habilitada para este tenant."""
