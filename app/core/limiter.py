"""
Rate limiting & concurrency control.

- `inference_semaphore`: Batasi concurrent ML inference agar tidak OOM.
  Dibuat lazy (saat pertama diakses) supaya selalu pada event loop yang benar.
- `limiter`: SlowAPI HTTP rate limiter per IP address.
"""
import asyncio
from slowapi import Limiter
from slowapi.util import get_remote_address

# HTTP rate limiter (SlowAPI) — dipasang ke app.state di main.py
limiter = Limiter(key_func=get_remote_address)

# ── Semaphore (lazy init) ─────────────────────────────────────────────────────
_semaphore: asyncio.Semaphore | None = None


def get_inference_semaphore() -> asyncio.Semaphore:
    """
    Kembalikan inference semaphore.
    Dibuat lazy agar selalu berada di running event loop yang benar.
    """
    global _semaphore
    if _semaphore is None:
        from app.core.config import settings
        _semaphore = asyncio.Semaphore(settings.INFERENCE_CONCURRENCY)
    return _semaphore
