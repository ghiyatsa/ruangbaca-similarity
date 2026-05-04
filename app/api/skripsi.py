"""
Router: CRUD Skripsi
=====================

Endpoint untuk membaca dan mengelola data skripsi.
Semua data masuk melalui sinkronisasi Laravel (lihat /api/v1/sync).

Endpoint di sini digunakan untuk:
  - Membaca / menampilkan data yang sudah tersinkron
  - Menghapus data jika diperlukan secara manual
"""
from __future__ import annotations

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.skripsi_repo import SkripsiRepository
from app.schemas.skripsi import SkripsiResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Baca
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=List[SkripsiResponse],
    summary="Daftar skripsi (dengan filter)",
    description="Ambil daftar skripsi yang sudah tersinkron dari Laravel.",
)
async def list_skripsi(
    db: AsyncSession = Depends(get_db),
    program_studi: Optional[str] = None,
    tahun: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[SkripsiResponse]:
    repo = SkripsiRepository(db)
    return await repo.list_all(
        program_studi=program_studi,
        tahun=tahun,
        limit=min(limit, 200),
        offset=offset,
    )


@router.get(
    "/{skripsi_id}",
    response_model=SkripsiResponse,
    summary="Detail satu skripsi",
)
async def get_skripsi(
    skripsi_id: int,
    db: AsyncSession = Depends(get_db),
) -> SkripsiResponse:
    repo    = SkripsiRepository(db)
    skripsi = await repo.find_by_id(skripsi_id)
    if not skripsi:
        raise HTTPException(status_code=404, detail="Skripsi tidak ditemukan.")
    return skripsi


# ─────────────────────────────────────────────────────────────────────────────
# Hapus
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/{skripsi_id}",
    status_code=204,
    summary="Hapus skripsi dari database dan vector store",
    description=(
        "Hapus data skripsi berdasarkan ID internal. "
        "Untuk hapus berdasarkan ID Laravel, gunakan endpoint `/sync/{laravel_id}`."
    ),
)
async def hapus_skripsi(
    request: Request,
    skripsi_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    vector_store = request.app.state.vector_store

    repo    = SkripsiRepository(db)
    skripsi = await repo.find_by_id(skripsi_id)
    if not skripsi:
        raise HTTPException(status_code=404, detail="Skripsi tidak ditemukan.")

    await repo.delete_by_id(skripsi_id)
    await db.commit()
    await vector_store.delete(skripsi_id)

    logger.info("Skripsi id=%d dihapus.", skripsi_id)
