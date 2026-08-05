"""Contrato de procesamiento de documentos (OCR, extraccion de texto/tablas).

Sin implementacion concreta: ningun agente del pedido original necesita leer
un PDF o una foto de una factura todavia. Cuando aparezca ese caso de uso
(OCR de un recibo de gasto, por ejemplo), un `DocumentProcessor` concreto se
agrega y se ofrece como una herramienta mas de la app correspondiente -- el
Core no necesita saber que es un documento, solo que una herramienta
devuelve datos estructurados, igual que cualquier otra.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentSource:
    content: bytes
    mime_type: str
    filename: str


@dataclass(frozen=True)
class DocumentExtraction:
    text: str
    tables: list[list[list[str]]]
    metadata: dict


class DocumentProcessor(ABC):
    @abstractmethod
    async def extract(self, document: DocumentSource) -> DocumentExtraction:
        """Extrae texto/tablas estructurados de un documento."""
