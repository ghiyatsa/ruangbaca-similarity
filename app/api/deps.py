"""
Shared FastAPI dependencies — dipusatkan di sini agar tidak tersebar di router.
"""
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

_bearer = HTTPBearer(auto_error=False)


async def verify_sync_token(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> None:
    """
    Validasi Bearer token yang dikirim Laravel.
    Token harus cocok dengan SYNC_SECRET di .env.
    Mengembalikan 401 jika token tidak ada atau tidak cocok.
    """
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or credentials.credentials != settings.SYNC_SECRET
    ):
        raise HTTPException(
            status_code=401,
            detail="Token sinkronisasi tidak valid.",
            headers={"WWW-Authenticate": "Bearer"},
        )
