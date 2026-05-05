"""
Repository layer untuk entitas Skripsi.

Memisahkan logika akses data dari router/endpoint agar:
- Unit testing lebih mudah
- SQL query tidak tersebar di seluruh kode
- Perubahan skema DB cukup di satu tempat
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skripsi import Skripsi
from app.schemas.skripsi import SyncItem


class SkripsiRepository:
    """Data access object untuk tabel `skripsi`."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_id(self, skripsi_id: int) -> Optional[Skripsi]:
        result = await self.db.execute(
            select(Skripsi).where(Skripsi.id == skripsi_id)
        )
        return result.scalar_one_or_none()

    async def find_by_source_id(self, skripsi_id: int) -> Optional[Skripsi]:
        result = await self.db.execute(
            select(Skripsi).where(Skripsi.skripsi_id == skripsi_id)
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

    async def upsert_from_sync(self, item: SyncItem) -> Skripsi:
        """
        Cari berdasarkan skripsi_id dari sistem sumber, update jika ada,
        atau buat baru jika belum ada.
        """
        skripsi = await self.find_by_source_id(item.skripsi_id)
        if skripsi:
            skripsi.skripsi_id = item.skripsi_id
            skripsi.judul = item.judul
            skripsi.abstrak = item.abstrak
            skripsi.kata_kunci = item.kata_kunci
            skripsi.tahun = item.tahun
            skripsi.program_studi = item.program_studi
            skripsi.nim = item.nim
            skripsi.nama_mahasiswa = item.nama_mahasiswa
        else:
            skripsi = Skripsi(**item.model_dump())
            self.db.add(skripsi)
        return skripsi

    async def delete_by_id(self, skripsi_id: int) -> None:
        await self.db.execute(delete(Skripsi).where(Skripsi.id == skripsi_id))

    async def delete_by_source_id(self, skripsi_id: int) -> None:
        await self.db.execute(
            delete(Skripsi).where(Skripsi.skripsi_id == skripsi_id)
        )
