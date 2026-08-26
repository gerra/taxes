"""Fernet encryption for documents at rest. Key comes from FERNET_KEY in secrets/.env."""

import os

from cryptography.fernet import Fernet

_fernet: Fernet | None = None


def _get() -> Fernet:
    global _fernet
    if _fernet is None:
        key = os.environ.get("FERNET_KEY", "")
        if not key:
            raise RuntimeError("FERNET_KEY is not set — required to store documents")
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt(data: bytes) -> bytes:
    return _get().encrypt(data)


def decrypt(data: bytes) -> bytes:
    return _get().decrypt(data)
