from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def phone_hash(phone: str) -> str:
    normalized = phone.strip()
    return hashlib.sha256((normalized + settings.server_salt).encode("utf-8")).hexdigest()


def _aes_key() -> bytes:
    return hashlib.sha256(settings.encryption_secret.encode("utf-8")).digest()


def encrypt_text(plain: str) -> str:
    if plain is None:
        return ""
    aesgcm = AESGCM(_aes_key())
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plain.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_text(token: str) -> str:
    if not token:
        return ""
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(_aes_key())
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


def mask_phone(phone: str) -> str:
    phone = phone.strip()
    if len(phone) < 7:
        return "****"
    return f"{phone[:3]}****{phone[-4:]}"
