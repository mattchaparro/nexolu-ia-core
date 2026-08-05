"""Contrato de voz a texto (speech-to-text).

Sin proveedor concreto, mismo criterio que `core/rag`: el POS actual ya deja
`speech.driver = null` a proposito (`config/ai.php`) porque el chat web
transcribe en el navegador y ningun canal soportado hoy manda audio crudo al
backend. El dia que WhatsApp/llamadas de voz entren al ecosistema, un
proveedor nuevo (OpenAI Whisper, Deepgram...) implementa esta interfaz y se
registra en un `SpeechProviderRegistry` analogo al de `providers/registry.py`,
sin tocar `core/chat`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioSource:
    content: bytes
    mime_type: str


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str | None = None


class SpeechToTextProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio: AudioSource) -> TranscriptionResult:
        """Convierte audio a texto."""
