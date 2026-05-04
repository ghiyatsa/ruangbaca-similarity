"""
Inisialisasi database — SQLite via aiosqlite.

Engine dan session factory dibuat sekali saat modul diimpor.
`init_db()` dipanggil sekali saat startup aplikasi.
`get_db()` digunakan sebagai FastAPI dependency di setiap endpoint.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings
from app.models.skripsi import Base

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    # SQLite: satu koneksi per waktu, check_same_thread=False agar aman di async
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Hindari lazy load setelah commit
    autoflush=False,
)


async def init_db() -> None:
    """Buat semua tabel jika belum ada."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI dependency: menyediakan sesi DB per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
