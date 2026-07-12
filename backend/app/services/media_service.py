from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

from app.core.config import settings


def signed_media_url(url: str | None, user_id: int, ttl_seconds: int = 600) -> str | None:
    if not url or not url.startswith("/api/media/"):
        return url
    expires = int(time.time()) + ttl_seconds
    public_id = url.rsplit("/", 1)[-1]
    payload = f"{public_id}:{user_id}:{expires}".encode()
    signature = hmac.new(settings.jwt_secret_key.encode(), payload, hashlib.sha256).hexdigest()
    return f"{url}?{urlencode({'uid': user_id, 'exp': expires, 'sig': signature})}"


def verify_media_signature(public_id: str, user_id: int, expires: int, signature: str) -> bool:
    if expires < int(time.time()):
        return False
    payload = f"{public_id}:{user_id}:{expires}".encode()
    expected = hmac.new(settings.jwt_secret_key.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
