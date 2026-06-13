"""
Router: Deteksi Kemiripan Judul Skripsi.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.limiter import limiter
from app.schemas.skripsi import (
    SimilarityCheckRequest,
    SimilarityCheckResponse,
    SimilarResult,
)
from app.utils.similarity import format_persen, get_similarity_level

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/check",
    response_model=SimilarityCheckResponse,
    summary="Cek kemiripan judul skripsi",
    description=(
        "Menerima judul saja lalu mencari skripsi yang paling mirip secara semantik. "
        "Response hanya mengembalikan `id` sumber dan skor similarity agar Laravel tetap menjadi source of truth data skripsi. "
        "Embedding dalam vector store dibangun dari judul, abstrak, dan kata kunci saat proses sinkronisasi. "
        "Rate limit: 10 request/menit per IP. "
        "Wajib menyertakan header Authorization: Bearer <SYNC_SECRET> atau X-Similarity-Api-Secret."
    ),
)
@limiter.limit("10/minute")
async def check_similarity(
    request: Request,
    body: SimilarityCheckRequest,
) -> SimilarityCheckResponse:
    embedding_service = request.app.state.embedding_service
    vector_store = request.app.state.vector_store

    total = await vector_store.count()
    if total == 0:
        raise HTTPException(
            status_code=404,
            detail="Belum ada data skripsi yang diindeks. Jalankan sinkronisasi terlebih dahulu.",
        )

    query_embedding = await embedding_service.encode_for_query(body.judul)
    raw_results = await vector_store.search(
        query_embedding=query_embedding,
        top_k=body.top_k,
    )

    results: list[SimilarResult] = []
    for result in raw_results:
        score = result["similarity_score"]
        if score < body.threshold:
            continue

        results.append(
            SimilarResult(
                id=result.get("skripsi_id", result["id"]),
                similarity_score=score,
                similarity_persen=format_persen(score),
                level=get_similarity_level(score),
            )
        )

    peringatan: str | None = None
    if results and results[0].similarity_score >= 0.85:
        peringatan = (
            f"Ditemukan judul dengan kemiripan SANGAT TINGGI "
            f"({results[0].similarity_persen}). "
            "Pertimbangkan untuk merevisi judul atau topik penelitian Anda."
        )

    logger.info(
        "Similarity check: '%s' -> %d hasil (threshold=%.2f).",
        body.judul[:60],
        len(results),
        body.threshold,
    )
    return SimilarityCheckResponse(
        query={"judul": body.judul},
        total_found=len(results),
        results=results,
        peringatan=peringatan,
    )


@router.post(
    "/compare",
    summary="Bandingkan dua judul secara langsung",
    description=(
        "Hitung cosine similarity antara dua judul skripsi tanpa membaca vector store. "
        "Endpoint ini berguna untuk evaluasi cepat atau debugging bobot/model."
    ),
)
@limiter.limit("20/minute")
async def compare_two(
    request: Request,
    judul_a: str,
    judul_b: str,
) -> dict:
    embedding_service = request.app.state.embedding_service

    emb_a = await embedding_service.encode_for_query(judul_a)
    emb_b = await embedding_service.encode_for_query(judul_b)
    score = embedding_service.cosine_similarity(emb_a, emb_b)

    return {
        "judul_a": judul_a,
        "judul_b": judul_b,
        "similarity_score": round(score, 4),
        "similarity_persen": format_persen(score),
        "level": get_similarity_level(score),
    }
