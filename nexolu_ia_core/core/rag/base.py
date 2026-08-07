"""Contratos de RAG (retrieval-augmented generation).

Sin implementacion concreta a proposito: hoy ningun agente del pedido
original (Cajero, Analista, Recepcionista, Soporte...) necesita recuperar
fragmentos de documentos -- sus respuestas salen de herramientas que
consultan datos estructurados. Construir un proveedor de embeddings o un
vector store ahora seria resolver un problema que todavia no existe.

Lo que si aporta valor hoy es dejar la interfaz lista: cuando haga falta
(manuales de producto, politicas internas, FAQs largas), `ChatOrchestrator`
solo necesita aceptar un `Retriever` opcional y agregar sus resultados al
contexto -- sin rediseñar nada de `core/chat`.

Persistencia: a definir cuando se implemente -- el motor de produccion es
MySQL (ver `core/memory/db.py`), asi que un vector store dedicado (o una
libreria de similitud en memoria si el volumen es chico) es mas realista
que depender de una extension especifica de otro motor.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Vectoriza una lista de textos."""


class RetrievedChunk:
    def __init__(self, text: str, score: float, metadata: dict | None = None) -> None:
        self.text = text
        self.score = score
        self.metadata = metadata or {}


class Retriever(ABC):
    @abstractmethod
    async def search(self, query: str, *, business_id: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Busca los fragmentos mas relevantes para `query`, acotados a un tenant."""
