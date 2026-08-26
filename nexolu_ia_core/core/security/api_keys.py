"""Helpers para el manejo no reversible/generacion de API keys de apps cliente.

Puerto directo de `nexolu_payments_core/core/security/api_keys.py`: mismo
algoritmo de hash (SHA-256) para que ambos servicios compartan el mismo
patron de autenticacion por hash.
"""
from __future__ import annotations

import hashlib
import secrets


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return f"iac_{secrets.token_urlsafe(32)}"
