"""
Router: Sinkronisasi dari Laravel
===================================

Endpoint dipanggil oleh Laravel melalui:
  - Observer (created / updated / deleted)
  - Artisan Command `php artisan skripsi:sync` (bulk sync)

Autentikasi: Bearer Token (SYNC_SECRET di .env)

Perbaikan dari v1:
  - Bulk-upsert diproses via BackgroundTask → HTTP langsung return 202
  - Repository pattern — SQL tidak di router
  - Fix N+1 db.refresh() → pakai flush() + expire_on_commit=False
  - verify_sync_token dipindah ke deps.py
"""
from __future__ import annotations

import logging
from itertools import islice
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.api.deps import verify_sync_token
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.repositories.skripsi_repo import SkripsiRepository
from app.schemas.skripsi import (
    BulkSyncRequest,
    BulkSyncResponse,
    SyncItem,
    SyncResponse,
)
from app.utils.metadata import build_metadata
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helper ────────────────────────────────────────────────────────────────────

def _chunked(iterable, n: int):
    """Bagi iterable menjadi potongan berukuran `n`."""
    it = iter(iterable)
    while chunk := list(islice(it, n)):
        yield chunk


# ── Background task untuk bulk-upsert ────────────────────────────────────────

async def _bulk_upsert_task(app_state, items: List[SyncItem]) -> None:
    """
    Proses bulk-upsert di background.
    Membuat DB session sendiri karena session dari request sudah ditutup.
    """
    embedding_service = app_state.embedding_service
    vector_store      = app_state.vector_store

    logger.info("Background bulk-upsert dimulai: %d item.", len(items))
    try:
        async with AsyncSessionLocal() as db:
            repo = SkripsiRepository(db)
            saved_pairs: List[tuple[SyncItem, object]] = []

            # Proses per chunk untuk kontrol memori
            for chunk in _chunked(items, settings.BULK_SYNC_CHUNK_SIZE):
                for item in chunk:
                    skripsi = await repo.upsert_from_sync(item)
                    saved_pairs.append((item, skripsi))
                await db.flush()  # dapat generated ID tanpa commit

            await db.commit()
            # Tidak perlu db.refresh() — expire_on_commit=False di AsyncSessionLocal

        # Batch encode (CPU heavy — semaphore sudah di dalam encode_batch_for_index)
        items_for_encode = [
            (s.judul, s.abstrak, s.kata_kunci) for _, s in saved_pairs
        ]
        embeddings = await embedding_service.encode_batch_for_index(items_for_encode)

        ids       = [item.laravel_id for item, _ in saved_pairs]
        metadatas = [build_metadata(item) for item, _ in saved_pairs]
        await vector_store.upsert_batch(ids, embeddings, metadatas)

        logger.info("Background bulk-upsert selesai: %d item berhasil.", len(saved_pairs))
    except Exception:
        logger.exception("Background bulk-upsert gagal.")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/upsert",
    response_model=SyncResponse,
    summary="Upsert satu skripsi dari Laravel",
    description=(
        "Dipanggil oleh **Laravel Observer** saat skripsi dibuat atau diperbarui. "
        "Wajib menyertakan header `Authorization: Bearer <SYNC_SECRET>`."
    ),
    dependencies=[Depends(verify_sync_token)],
)
async def upsert_one(
    request: Request,
    body: SyncItem,
    db: AsyncSession = Depends(get_db),
) -> SyncResponse:
    embedding_service = request.app.state.embedding_service
    vector_store      = request.app.state.vector_store

    repo    = SkripsiRepository(db)
    skripsi = await repo.upsert_from_sync(body)
    await db.commit()

    embedding = await embedding_service.encode_for_index(
        judul=skripsi.judul,
        abstrak=skripsi.abstrak,
        kata_kunci=skripsi.kata_kunci,
    )
    await vector_store.upsert(
        skripsi_id=body.laravel_id,
        embedding=embedding,
        metadata=build_metadata(body),
    )

    logger.info("Upsert skripsi laravel_id=%d selesai.", body.laravel_id)
    return SyncResponse(
        message="Skripsi berhasil di-upsert",
        laravel_id=body.laravel_id,
        local_id=skripsi.id,
    )


@router.post(
    "/bulk-upsert",
    status_code=202,
    response_model=BulkSyncResponse,
    summary="Bulk upsert skripsi dari Laravel (async)",
    description=(
        "Dipanggil oleh `php artisan skripsi:sync`. "
        "Proses berjalan di **background** — response 202 dikembalikan segera. "
        "Wajib menyertakan header `Authorization: Bearer <SYNC_SECRET>`."
    ),
    dependencies=[Depends(verify_sync_token)],
)
async def bulk_upsert(
    request: Request,
    body: BulkSyncRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    if not body.data:
        raise HTTPException(status_code=400, detail="Data tidak boleh kosong.")

    background_tasks.add_task(_bulk_upsert_task, request.app.state, body.data)
    logger.info("Bulk-upsert diterima: %d item — diproses di background.", len(body.data))

    return BulkSyncResponse(
        message=f"Menerima {len(body.data)} item — sedang diproses di background.",
        status="accepted",
        total_received=len(body.data),
    )


@router.delete(
    "/{laravel_id}",
    status_code=204,
    summary="Hapus skripsi berdasarkan laravel_id",
    description=(
        "Dipanggil oleh **Laravel Observer** saat skripsi dihapus. "
        "Wajib menyertakan header `Authorization: Bearer <SYNC_SECRET>`."
    ),
    dependencies=[Depends(verify_sync_token)],
)
async def delete_by_laravel_id(
    request: Request,
    laravel_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    vector_store = request.app.state.vector_store

    repo = SkripsiRepository(db)
    await repo.delete_by_laravel_id(laravel_id)
    await db.commit()
    await vector_store.delete(laravel_id)

    logger.info("Skripsi laravel_id=%d dihapus.", laravel_id)
