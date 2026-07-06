"""
Router: Deteksi Kemiripan Judul Skripsi.
"""
from __future__ import annotations

import logging
from collections import Counter

from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings
from app.core.limiter import limiter
from app.schemas.document import (
    SimilarityCheckRequest,
    SimilarityCheckResponse,
    SimilarResult,
)
from app.utils.similarity import calculate_jaccard, format_persen, get_similarity_level

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
        document_type=body.document_type,
    )

    results: list[SimilarResult] = []
    for result in raw_results:
        # Calculate Jaccard lexical similarity of cleaned titles
        db_title = result.get("document", "")
        cleaned_query = embedding_service.clean_title(body.judul)
        cleaned_db = embedding_service.clean_title(db_title)
        
        jaccard_score = calculate_jaccard(cleaned_query, cleaned_db)
            
        semantic_score = result["similarity_score"]
        hybrid_score = (settings.HYBRID_SEMANTIC_WEIGHT * semantic_score) + (settings.HYBRID_LEXICAL_WEIGHT * jaccard_score)
        hybrid_score = round(hybrid_score, 4)

        if hybrid_score < body.threshold:
            continue

        doc_id_str = result.get("document_id", str(result["id"]))
        if "_" in doc_id_str:
            parts = doc_id_str.split("_")
            try:
                doc_id = int(parts[-1])
                doc_type = "_".join(parts[:-1])
            except ValueError:
                doc_id = 0
                doc_type = "unknown"
        else:
            doc_id = int(doc_id_str) if doc_id_str.isdigit() else 0
            doc_type = result.get("document_type", "skripsi")

        results.append(
            SimilarResult(
                id=doc_id_str,
                document_id=doc_id,
                document_type=doc_type,
                skripsi_id=doc_id if doc_type == "skripsi" else None,
                similarity_score=hybrid_score,
                similarity_persen=format_persen(hybrid_score),
                level=get_similarity_level(hybrid_score),
            )
        )

    # Sort results by hybrid_score descending just in case Jaccard shifted order
    results.sort(key=lambda x: x.similarity_score, reverse=True)

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
@limiter.limit("200/minute")
async def compare_two(
    request: Request,
    judul_a: str,
    judul_b: str,
) -> dict:
    embedding_service = request.app.state.embedding_service

    emb_a = await embedding_service.encode_for_query(judul_a)
    emb_b = await embedding_service.encode_for_query(judul_b)
    score_semantic = embedding_service.cosine_similarity(emb_a, emb_b)

    cleaned_a = embedding_service.clean_title(judul_a)
    cleaned_b = embedding_service.clean_title(judul_b)
    jaccard_score = calculate_jaccard(cleaned_a, cleaned_b)

    score_hybrid = (settings.HYBRID_SEMANTIC_WEIGHT * score_semantic) + (settings.HYBRID_LEXICAL_WEIGHT * jaccard_score)
    score_hybrid = round(score_hybrid, 4)

    return {
        "judul_a": judul_a,
        "judul_b": judul_b,
        "similarity_score": score_hybrid,
        "similarity_persen": format_persen(score_hybrid),
        "level": get_similarity_level(score_hybrid),
        "detail": {
            "semantic_score": round(score_semantic, 4),
            "lexical_score": round(jaccard_score, 4)
        }
    }


@router.get(
    "/stats",
    summary="Statistik metadata sebaran skripsi",
    description="Mengembalikan agregasi data per program studi dan per tahun dari metadata vector store untuk keperluan bab statistik laporan.",
)
async def get_stats(request: Request) -> dict:
    vector_store = request.app.state.vector_store
    
    total = await vector_store.count()
    if total == 0:
        return {
            "total_indexed": 0,
            "distribusi_program_studi": {},
            "distribusi_tahun": {},
        }
        
    # Ambil maksimal 10.000 data di database untuk agregasi lokal
    results = await vector_store._run(
        vector_store.collection.get,
        limit=10000,
        include=["metadatas"]
    )
    
    metadatas = results.get("metadatas", [])
    
    prodi_list = []
    tahun_list = []
    
    for meta in metadatas:
        if not meta:
            continue
        prodi = meta.get("program_studi", "Tidak Diketahui")
        tahun = meta.get("tahun", 0)
        prodi_list.append(prodi)
        if tahun and tahun > 0:
            tahun_list.append(str(tahun))
            
    return {
        "total_indexed": total,
        "distribusi_program_studi": dict(Counter(prodi_list)),
        "distribusi_tahun": dict(Counter(tahun_list)),
    }

