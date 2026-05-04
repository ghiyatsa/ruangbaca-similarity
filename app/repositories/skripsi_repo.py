"""
Repository layer untuk entitas Skripsi.

Memisahkan logika akses data dari router/endpoint agar:
- Unit testing lebih mudah (inject mock repository)
- SQL query tidak tersebar di seluruh kode
- Perubahan skema DB cukup di satu tempat

Sumber data: hanya dari sinkronisasi Laravel (via SyncItem).
"""
from __future__ import annotations

import logging
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.skripsi import Skripsi
from app.schemas.skripsi import SyncItem

logger = logging.getLogger(__name__)


class SkripsiRepository:
    """Data access object untuk tabel `skripsi`."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Read ───────────────────────────────────────────────────────────────────

    async def find_by_id(self, skripsi_id: int) -> Optional[Skripsi]:
        result = await self.db.execute(
            select(Skripsi).where(Skripsi.id == skripsi_id)
        )
        return result.scalar_one_or_none()

    async def find_by_laravel_id(self, laravel_id: int) -> Optional[Skripsi]:
        result = await self.db.execute(
            select(Skripsi).where(Skripsi.laravel_id == laravel_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        program_studi: Optional[str] = None,
        tahun: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Skripsi]:
        query = select(Skripsi)
        if program_studi:
            query = query.where(Skripsi.program_studi == program_studi)
        if tahun:
            query = query.where(Skripsi.tahun == tahun)
        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ── Write ──────────────────────────────────────────────────────────────────

    async def upsert_from_sync(self, item: SyncItem) -> Skripsi:
        """
        Cari berdasarkan laravel_id, update jika ada — buat baru jika tidak.
        Tidak melakukan commit; caller yang bertanggung jawab.
        """
        skripsi = await self.find_by_laravel_id(item.laravel_id)
        if skripsi:
            skripsi.judul          = item.judul
            skripsi.abstrak        = item.abstrak
            skripsi.kata_kunci     = item.kata_kunci
            skripsi.tahun          = item.tahun
            skripsi.program_studi  = item.program_studi
            skripsi.nim            = item.nim
            skripsi.nama_mahasiswa = item.nama_mahasiswa
        else:
            skripsi = Skripsi(**item.model_dump())
            self.db.add(skripsi)
        return skripsi

    # ── Delete ─────────────────────────────────────────────────────────────────

    async def delete_by_id(self, skripsi_id: int) -> None:
        await self.db.execute(delete(Skripsi).where(Skripsi.id == skripsi_id))

    async def delete_by_laravel_id(self, laravel_id: int) -> None:
        await self.db.execute(
            delete(Skripsi).where(Skripsi.laravel_id == laravel_id)
        )
