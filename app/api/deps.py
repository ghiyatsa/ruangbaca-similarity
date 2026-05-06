"""
Shared FastAPI dependencies dipusatkan di sini agar tidak tersebar di router.
"""
import secrets

from fastapi import Header, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

_bearer = HTTPBearer(auto_error=False)


async def verify_sync_token(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    x_similarity_api_secret: str | None = Header(None, alias="X-Similarity-Api-Secret"),
) -> None:
    """
    Validasi token yang dikirim Laravel.
    Mendukung dua mekanisme:
    1. Header 'Authorization: Bearer <token>' (Standard)
    2. Header 'X-Similarity-Api-Secret: <token>' (Digunakan jika Bearer dipakai oleh HF Space)

    Token harus cocok dengan SYNC_SECRET di .env.
    """
    # 1. Cek custom header dulu (prioritas untuk HF Space environment)
    if x_similarity_api_secret and secrets.compare_digest(
        x_similarity_api_secret, settings.SYNC_SECRET
    ):
        return

    # 2. Cek Bearer token (fallback untuk local/direct access)
    if (
        credentials
        and credentials.scheme.lower() == "bearer"
        and secrets.compare_digest(credentials.credentials, settings.SYNC_SECRET)
    ):
        return

    # 3. Jika tidak ada yang cocok
    raise HTTPException(
        status_code=401,
        detail="Token sinkronisasi tidak valid atau tidak ditemukan.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    """
    Validasi Bearer token yang dikirim Laravel.
    Token harus cocok dengan SYNC_SECRET di .env.
    Mengembalikan 401 jika token tidak ada atau tidak cocok.
    """
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, settings.SYNC_SECRET)
    ):
        raise HTTPException(
            status_code=401,
            detail="Token sinkronisasi tidak valid.",
            headers={"WWW-Authenticate": "Bearer"},
        )
