"""
Router: Sinkronisasi dari Laravel.
"""
from __future__ import annotations

import asyncio
import json
import logging
from itertools import islice
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import verify_sync_token
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.repositories.skripsi_repo import SkripsiRepository
from app.repositories.sync_job_repo import SyncJobRepository
from app.schemas.skripsi import (
    BulkSyncJobStatusResponse,
    BulkSyncRequest,
    BulkSyncResponse,
    SyncItem,
    SyncResponse,
)
from app.utils.metadata import build_metadata

logger = logging.getLogger(__name__)
router = APIRouter()


def _chunked(iterable, size: int):
    """Bagi iterable menjadi potongan berukuran `size`."""
    iterator = iter(iterable)
    while chunk := list(islice(iterator, size)):
        yield chunk


def _serialize_items(items: List[SyncItem]) -> str:
    return json.dumps(
        [item.model_dump(mode="json", by_alias=True) for item in items],
        ensure_ascii=False,
    )


def _deserialize_items(payload_json: str) -> List[SyncItem]:
    return [SyncItem.model_validate(item) for item in json.loads(payload_json)]


async def _run_bulk_upsert_job(app_state, job_id: str) -> None:
    embedding_service = app_state.embedding_service
    vector_store = app_state.vector_store

    logger.info("Bulk-upsert job dimulai: %s", job_id)

    async with AsyncSessionLocal() as db:
        job_repo = SyncJobRepository(db)
        job = await job_repo.find_by_id(job_id)

        if job is None:
            logger.warning("Bulk-upsert job tidak ditemukan: %s", job_id)
            return

        items = _deserialize_items(job.payload_json)
        await job_repo.mark_processing(job)
        await db.commit()

    processed = 0

    try:
        for chunk in _chunked(items, settings.BULK_SYNC_CHUNK_SIZE):
            async with AsyncSessionLocal() as db:
                skripsi_repo = SkripsiRepository(db)
                saved_pairs: List[tuple[SyncItem, object]] = []

                for item in chunk:
                    skripsi = await skripsi_repo.upsert_from_sync(item)
                    saved_pairs.append((item, skripsi))

                await db.commit()

            items_for_encode = [
                (
                    record.judul,
                    record.abstrak,
                    record.kata_kunci,
                    item.bobot_judul,
                    item.bobot_abstrak,
                    item.bobot_kata_kunci,
                )
                for item, record in saved_pairs
            ]
            embeddings = await embedding_service.encode_batch_for_index(items_for_encode)

            ids = [item.skripsi_id for item, _ in saved_pairs]
            metadatas = [build_metadata(item) for item, _ in saved_pairs]
            await vector_store.upsert_batch(ids, embeddings, metadatas)

            processed += len(chunk)

            async with AsyncSessionLocal() as db:
                job_repo = SyncJobRepository(db)
                job = await job_repo.find_by_id(job_id)
                if job is not None:
                    await job_repo.update_progress(job, processed)
                    await db.commit()

        async with AsyncSessionLocal() as db:
            job_repo = SyncJobRepository(db)
            job = await job_repo.find_by_id(job_id)
            if job is not None:
                await job_repo.mark_completed(job)
                await db.commit()

        logger.info("Bulk-upsert job selesai: %s", job_id)
    except Exception as exception:
        logger.exception("Bulk-upsert job gagal: %s", job_id)

        async with AsyncSessionLocal() as db:
            job_repo = SyncJobRepository(db)
            job = await job_repo.find_by_id(job_id)
            if job is not None:
                await job_repo.mark_failed(job, str(exception))
                await db.commit()


async def resume_unfinished_jobs(app_state) -> None:
    async with AsyncSessionLocal() as db:
        jobs = await SyncJobRepository(db).list_unfinished()

    for job in jobs:
        asyncio.create_task(_run_bulk_upsert_job(app_state, job.id))

    if jobs:
        logger.info("Menjadwalkan ulang %d bulk-upsert job yang belum selesai.", len(jobs))


@router.post(
    "/upsert",
    response_model=SyncResponse,
    summary="Upsert satu skripsi dari Laravel",
    description=(
        "Dipanggil oleh Laravel Observer saat skripsi dibuat atau diperbarui. "
        "Wajib menyertakan header Authorization: Bearer <SYNC_SECRET> atau X-Similarity-Api-Secret."
    ),
    dependencies=[Depends(verify_sync_token)],
)
async def upsert_one(
    request: Request,
    body: SyncItem,
    db: AsyncSession = Depends(get_db),
) -> SyncResponse:
    embedding_service = request.app.state.embedding_service
    vector_store = request.app.state.vector_store

    repo = SkripsiRepository(db)
    skripsi = await repo.upsert_from_sync(body)
    await db.commit()

    embedding = await embedding_service.encode_for_index(
        judul=skripsi.judul,
        abstrak=skripsi.abstrak,
        kata_kunci=skripsi.kata_kunci,
        bobot_judul=body.bobot_judul,
        bobot_abstrak=body.bobot_abstrak,
        bobot_kata_kunci=body.bobot_kata_kunci,
    )
    await vector_store.upsert(
        skripsi_id=body.skripsi_id,
        embedding=embedding,
        metadata=build_metadata(body),
    )

    logger.info("Upsert skripsi skripsi_id=%d selesai.", body.skripsi_id)
    return SyncResponse(
        message="Skripsi berhasil di-upsert",
        skripsi_id=body.skripsi_id,
        local_id=skripsi.id,
    )


@router.post(
    "/bulk-upsert",
    status_code=202,
    response_model=BulkSyncResponse,
    summary="Bulk upsert skripsi dari Laravel (async)",
    description=(
        "Dipanggil oleh php artisan skripsi:sync. "
        "Payload disimpan sebagai job persisten dan diproses async. "
        "Gunakan endpoint status job untuk memantau hasil akhirnya. "
        "Wajib menyertakan header Authorization: Bearer <SYNC_SECRET> atau X-Similarity-Api-Secret."
    ),
    dependencies=[Depends(verify_sync_token)],
)
async def bulk_upsert(
    request: Request,
    body: BulkSyncRequest,
    db: AsyncSession = Depends(get_db),
) -> BulkSyncResponse:
    if not body.data:
        raise HTTPException(status_code=400, detail="Data tidak boleh kosong.")

    job_id = str(uuid4())
    payload_json = _serialize_items(body.data)
    job_repo = SyncJobRepository(db)
    await job_repo.create(
        job_id=job_id,
        payload_json=payload_json,
        total_received=len(body.data),
    )
    await db.commit()

    asyncio.create_task(_run_bulk_upsert_job(request.app.state, job_id))
    logger.info("Bulk-upsert diterima: job_id=%s total=%d", job_id, len(body.data))

    return BulkSyncResponse(
        message=f"Menerima {len(body.data)} item dan job sedang diproses.",
        status="accepted",
        total_received=len(body.data),
        job_id=job_id,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=BulkSyncJobStatusResponse,
    summary="Lihat status bulk upsert job",
    description="Mengembalikan status akhir atau progress dari bulk sync yang sebelumnya diterima.",
    dependencies=[Depends(verify_sync_token)],
)
async def show_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> BulkSyncJobStatusResponse:
    job = await SyncJobRepository(db).find_by_id(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")

    return BulkSyncJobStatusResponse(
        job_id=job.id,
        status=job.status,
        total_received=job.total_received,
        total_processed=job.total_processed,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.delete(
    "/{skripsi_id}",
    status_code=204,
    summary="Hapus skripsi berdasarkan skripsi_id sumber",
    description=(
        "Dipanggil oleh Laravel Observer saat skripsi dihapus. "
        "Wajib menyertakan header Authorization: Bearer <SYNC_SECRET> atau X-Similarity-Api-Secret."
    ),
    dependencies=[Depends(verify_sync_token)],
)
async def delete_by_skripsi_id(
    request: Request,
    skripsi_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    vector_store = request.app.state.vector_store

    repo = SkripsiRepository(db)
    await repo.delete_by_source_id(skripsi_id)
    await db.commit()
    await vector_store.delete(skripsi_id)

    logger.info("Skripsi skripsi_id=%d dihapus.", skripsi_id)
