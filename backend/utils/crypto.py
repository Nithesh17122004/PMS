"""Field-level encryption and blind indexes for sensitive patient data."""
from __future__ import annotations

import hashlib
import hmac
import re

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

_cipher_cache: dict[str, Fernet] = {}


def _cipher() -> Fernet:
    key = current_app.config["FIELD_ENCRYPTION_KEY"]
    if key not in _cipher_cache:
        _cipher_cache[key] = Fernet(key.encode() if isinstance(key, str) else key)
    return _cipher_cache[key]


def encrypt_value(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return _cipher().encrypt(str(value).encode("utf-8")).decode("ascii")


def decrypt_value(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        # Data written with a rotated/incorrect key must not crash the app.
        return None


def blind_index(value: str | None) -> str | None:
    if not value:
        return None
    key = current_app.config["BLIND_INDEX_KEY"].encode()
    return hmac.new(key, str(value).encode("utf-8"), hashlib.sha256).hexdigest()


def normalize_phone(value: str | None) -> str:
    if not value:
        return ""
    digits = re.sub(r"\D", "", str(value))
    return digits[-15:]


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def mask_email(value: str | None) -> str:
    if not value or "@" not in value:
        return value or ""
    name, domain = value.split("@", 1)
    if len(name) <= 2:
        masked = name[:1] + "*"
    else:
        masked = name[:2] + "*" * max(1, len(name) - 2)
    return f"{masked}@{domain}"


def mask_phone(value: str | None) -> str:
    digits = normalize_phone(value)
    if len(digits) < 4:
        return "****"
    return "*" * max(0, len(digits) - 4) + digits[-4:]


class EncryptedString(TypeDecorator):
    """Transparently encrypts a string column at rest (Fernet)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        return decrypt_value(value)
