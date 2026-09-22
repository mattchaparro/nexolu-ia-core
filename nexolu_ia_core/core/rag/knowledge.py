"""Lo que el bot sabe de cada negocio: preguntas frecuentes editables.

Primera implementacion concreta del `Retriever` de `core/rag/base.py`, y a
proposito la mas simple que resuelve el problema real: un salon tiene
decenas de preguntas frecuentes, no miles de documentos. Con ese volumen,
lo correcto es darle al modelo TODAS las activas en el prompt; no hay
nada que "recuperar" y un vector store seria resolver un problema que
todavia no existe.

Cuando un negocio pase del presupuesto de caracteres, se eligen las mas
parecidas al mensaje (palabras en comun, sin tildes). El dia que eso se
quede corto, se cambia `select_relevant` por embeddings sin tocar a
quien lo llama: el contrato ya es el de `Retriever`.
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexolu_ia_core.core.memory.entities import KnowledgeEntry
from nexolu_ia_core.core.rag.base import RetrievedChunk, Retriever

# Cuanto conocimiento entra al prompt, en caracteres. Unas 40 respuestas
# medianas: holgado para un salon, y acotado para que un negocio que pegue
# su manual entero no se coma el contexto de la conversacion.
PROMPT_BUDGET_CHARS = 6000

# Palabras que no dicen de que se habla.
_STOPWORDS = {
    "a", "al", "algo", "como", "con", "cual", "cuales", "cuanto", "de", "del", "el", "en",
    "es", "hay", "la", "las", "lo", "los", "me", "mi", "para", "por", "que", "se", "si",
    "su", "tienen", "tiene", "un", "una", "y", "yo", "o", "le", "les", "no", "son",
}


def _words(text: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]+", plain) if len(w) > 2 and w not in _STOPWORDS}


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, app_id: str, business_id: str) -> list[KnowledgeEntry]:
        stmt = (
            select(KnowledgeEntry)
            .where(KnowledgeEntry.app_id == app_id, KnowledgeEntry.business_id == business_id)
            .order_by(KnowledgeEntry.topic)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def active(self, app_id: str, business_id: str) -> list[KnowledgeEntry]:
        return [e for e in await self.list(app_id, business_id) if e.is_active]

    async def get(self, entry_id: str, app_id: str, business_id: str) -> KnowledgeEntry | None:
        # Filtro por app + negocio aunque el id venga en la URL: nadie edita
        # el conocimiento de otro tenant probando ids.
        stmt = select(KnowledgeEntry).where(
            KnowledgeEntry.id == entry_id,
            KnowledgeEntry.app_id == app_id,
            KnowledgeEntry.business_id == business_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(self, **fields) -> KnowledgeEntry:
        entry = KnowledgeEntry(**fields)
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def delete(self, entry: KnowledgeEntry) -> None:
        await self._session.delete(entry)
        await self._session.flush()


def select_relevant(entries: list[KnowledgeEntry], query: str, budget: int = PROMPT_BUDGET_CHARS) -> list[KnowledgeEntry]:
    """Las que entran al prompt: todas si caben; si no, las más parecidas."""
    if sum(len(e.topic) + len(e.answer) for e in entries) <= budget:
        return entries

    asked = _words(query)
    ranked = sorted(
        entries,
        key=lambda e: len(asked & _words(f"{e.topic} {e.answer}")),
        reverse=True,
    )

    chosen: list[KnowledgeEntry] = []
    used = 0
    for entry in ranked:
        size = len(entry.topic) + len(entry.answer)
        if used + size > budget:
            continue
        chosen.append(entry)
        used += size
    return chosen


def render_for_prompt(entries: list[KnowledgeEntry]) -> str:
    return "\n".join(f"- {e.topic}: {e.answer.strip()}" for e in entries)


class KnowledgeRetriever(Retriever):
    """El `Retriever` del contrato, para quien lo quiera usar como tal."""

    def __init__(self, repository: KnowledgeRepository, app_id: str) -> None:
        self._repository = repository
        self._app_id = app_id

    async def search(self, query: str, *, business_id: str, top_k: int = 5) -> list[RetrievedChunk]:
        entries = select_relevant(await self._repository.active(self._app_id, business_id), query)
        return [RetrievedChunk(f"{e.topic}: {e.answer}", 1.0, {"id": e.id}) for e in entries[:top_k]]
