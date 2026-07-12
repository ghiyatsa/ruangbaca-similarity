"""
Modul pembatasan laju permintaan (rate limiting) dan kontrol konkurensi.
Menyediakan mekanisme pencegahan kelebihan beban kerja memori (Out-Of-Memory)
dan pembatasan laju lalu lintas HTTP per alamat IP.
"""
import asyncio
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

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
