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

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import verify_sync_token
from app.core.config import settings
from app.repositories.sync_job_repo import SyncJobRepository
from app.schemas.skripsi import (
    BulkSyncJobStatusResponse,
    BulkSyncRequest,
    BulkSyncResponse,
    IndexedIdsResponse,
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


def _serialize_payload(items: List[SyncItem], reset_index: bool) -> str:
    return json.dumps(
        {
            "data": [item.model_dump(mode="json", by_alias=True) for item in items],
            "reset_index": reset_index,
        },
        ensure_ascii=False,
    )


def _deserialize_payload(payload_json: str) -> tuple[List[SyncItem], bool]:
    payload = json.loads(payload_json)

    if isinstance(payload, list):
        return [SyncItem.model_validate(item) for item in payload], False

    return [
        SyncItem.model_validate(item)
        for item in payload.get("data", [])
    ], bool(payload.get("reset_index", False))


async def _run_bulk_upsert_job(app_state, job_id: str) -> None:
    embedding_service = app_state.embedding_service
    vector_store = app_state.vector_store

    logger.info("Bulk-upsert job dimulai: %s", job_id)

    job = await SyncJobRepository.find_by_id(job_id)

    if job is None:
        logger.warning("Bulk-upsert job tidak ditemukan: %s", job_id)
        return

    payload_json = job.__dict__.get("_payload_json", "{}")
    items, reset_index = _deserialize_payload(payload_json)
    await SyncJobRepository.mark_processing(job)

    processed = 0
    expected_total = len({item.skripsi_id for item in items})

    try:
        if reset_index:
            await vector_store.reset()
            logger.info("Bulk-upsert job %s menjalankan reset penuh sebelum reindex.", job_id)

        for chunk in _chunked(items, settings.BULK_SYNC_CHUNK_SIZE):
            items_for_encode = [
                (
                    item.judul,
                    item.abstrak,
                    item.kata_kunci,
                    item.bobot_judul,
                    item.bobot_abstrak,
                    item.bobot_kata_kunci,
                )
                for item in chunk
            ]
            embeddings = await embedding_service.encode_batch_for_index(items_for_encode)

            ids = [item.skripsi_id for item in chunk]
            metadatas = [build_metadata(item) for item in chunk]
            await vector_store.upsert_batch(ids, embeddings, metadatas)

            processed += len(chunk)

            job = await SyncJobRepository.find_by_id(job_id)
            if job is not None:
                await SyncJobRepository.update_progress(job, processed)

        total_indexed = await vector_store.count()

        if reset_index:
            if total_indexed != expected_total:
                raise RuntimeError(
                    "Jumlah vector hasil reindex tidak konsisten "
                    f"(expected={expected_total}, vector={total_indexed})."
                )
        elif total_indexed < expected_total:
            raise RuntimeError(
                "Jumlah vector terindeks lebih kecil dari data yang diterima "
                f"(received={expected_total}, vector={total_indexed})."
            )

        job = await SyncJobRepository.find_by_id(job_id)
        if job is not None:
            await SyncJobRepository.mark_completed(job)

        logger.info("Bulk-upsert job selesai: %s", job_id)
    except Exception as exception:
        logger.exception("Bulk-upsert job gagal: %s", job_id)

        job = await SyncJobRepository.find_by_id(job_id)
        if job is not None:
            await SyncJobRepository.mark_failed(job, str(exception))


async def resume_unfinished_jobs(app_state) -> None:
    jobs = await SyncJobRepository.list_unfinished()

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
        "Endpoint ini tidak menyimpan data skripsi penuh ke database lokal; service hanya membuat embedding dan memperbarui vector store. "
        "Wajib menyertakan header Authorization: Bearer <SYNC_SECRET> atau X-Similarity-Api-Secret."
    ),
    dependencies=[Depends(verify_sync_token)],
)
async def upsert_one(
    request: Request,
    body: SyncItem,
) -> SyncResponse:
    embedding_service = request.app.state.embedding_service
    vector_store = request.app.state.vector_store

    embedding = await embedding_service.encode_for_index(
        judul=body.judul,
        abstrak=body.abstrak,
        kata_kunci=body.kata_kunci,
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
    )


@router.post(
    "/bulk-upsert",
    status_code=202,
    response_model=BulkSyncResponse,
    summary="Bulk upsert skripsi dari Laravel (async)",
    description=(
        "Dipanggil oleh php artisan skripsi:sync. "
        "Payload disimpan sebagai job persisten lalu diproses async untuk membangun ulang atau memperbarui vector index. "
        "Gunakan endpoint status job untuk memantau hasil akhirnya. "
        "Wajib menyertakan header Authorization: Bearer <SYNC_SECRET> atau X-Similarity-Api-Secret."
    ),
    dependencies=[Depends(verify_sync_token)],
)
async def bulk_upsert(
    request: Request,
    body: BulkSyncRequest,
) -> BulkSyncResponse:
    if not body.data:
        raise HTTPException(status_code=400, detail="Data tidak boleh kosong.")

    job_id = str(uuid4())
    payload_json = _serialize_payload(body.data, body.reset_index)
    await SyncJobRepository.create(
        job_id=job_id,
        payload_json=payload_json,
        total_received=len(body.data),
    )

    asyncio.create_task(_run_bulk_upsert_job(request.app.state, job_id))
    logger.info(
        "Bulk-upsert diterima: job_id=%s total=%d reset_index=%s",
        job_id,
        len(body.data),
        body.reset_index,
    )

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
) -> BulkSyncJobStatusResponse:
    job = await SyncJobRepository.find_by_id(job_id)

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


@router.get(
    "/indexed-ids",
    response_model=IndexedIdsResponse,
    summary="Daftar skripsi yang sudah terindeks",
    description=(
        "Mengembalikan daftar `skripsi_id` yang saat ini tersimpan di vector store. "
        "Endpoint ini dipakai Laravel untuk rekonsiliasi status sync berdasarkan ID sumber, bukan berdasarkan count mentah."
    ),
    dependencies=[Depends(verify_sync_token)],
)
async def indexed_ids(
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> IndexedIdsResponse:
    vector_store = request.app.state.vector_store

    total_indexed = await vector_store.count()
    ids = await vector_store.indexed_ids(limit=limit, offset=offset)

    next_offset = offset + len(ids)
    if next_offset >= total_indexed:
        next_offset = None

    return IndexedIdsResponse(
        ids=ids,
        total_indexed=total_indexed,
        next_offset=next_offset,
    )


@router.delete(
    "/{skripsi_id}",
    status_code=204,
    summary="Hapus skripsi berdasarkan skripsi_id sumber",
    description=(
        "Dipanggil oleh Laravel Observer saat skripsi dihapus. "
        "Endpoint ini idempotent: jika ID tidak ada di vector store, respons tetap 204 karena kondisi akhir sudah benar. "
        "Wajib menyertakan header Authorization: Bearer <SYNC_SECRET> atau X-Similarity-Api-Secret."
    ),
    dependencies=[Depends(verify_sync_token)],
)
async def delete_by_skripsi_id(
    request: Request,
    skripsi_id: int,
) -> None:
    vector_store = request.app.state.vector_store

    await vector_store.delete(skripsi_id)

    logger.info("Skripsi skripsi_id=%d dihapus.", skripsi_id)
