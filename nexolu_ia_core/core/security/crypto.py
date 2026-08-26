"""Cifrado en reposo de credenciales sensibles (API keys de apps, workspace
keys de proveedor).

Puerto directo de `nexolu_payments_core/core/security/crypto.py`: Fernet
(AES128 + HMAC, con rotacion de nonce por valor) usando una unica clave de
proceso (`IA_CORE_MASTER_KEY`), nunca guardada en la base. Un dump de la BD
o un acceso de solo lectura mal configurado no debe entregar esos secretos
en texto plano.
"""
from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from nexolu_ia_core.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().ia_core_master_key
    if not key:
        raise RuntimeError(
            "IA_CORE_MASTER_KEY no esta configurada: no se pueden leer ni "
            "escribir credenciales de apps. Generarla con "
            "`python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())"`.'
        )
    return Fernet(key.encode())


class EncryptedString(TypeDecorator):
    """Columna String que cifra al escribir y descifra al leer, de forma
    transparente para el resto del codigo (los modelos la usan como un
    `Mapped[str]` normal)."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return _fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return _fernet().decrypt(value.encode()).decode()
