"""
Inisialisasi database SQLite via aiosqlite.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.skripsi import Base

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def _migrate_legacy_skripsi_id_column() -> None:
    """
    Migrasi ringan untuk database lama yang masih memakai kolom `laravel_id`.
    """
    if "sqlite" not in settings.DATABASE_URL:
        return

    async with engine.begin() as conn:
        table_exists = (
            await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='skripsi'")
            )
        ).scalar_one_or_none()
        if not table_exists:
            return

        result = await conn.execute(text("PRAGMA table_info(skripsi)"))
        columns = {row[1] for row in result.fetchall()}

        if "laravel_id" in columns and "skripsi_id" not in columns:
            await conn.execute(text("ALTER TABLE skripsi RENAME COLUMN laravel_id TO skripsi_id"))
            await conn.execute(text("DROP INDEX IF EXISTS ix_skripsi_laravel_id"))
            await conn.execute(text("DROP INDEX IF EXISTS ix_skripsi_skripsi_id"))
            await conn.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_skripsi_skripsi_id ON skripsi (skripsi_id)")
            )


async def init_db() -> None:
    """Migrasikan schema ringan lalu buat semua tabel jika belum ada."""
    await _migrate_legacy_skripsi_id_column()
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
