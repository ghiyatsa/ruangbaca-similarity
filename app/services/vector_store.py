"""
VectorStore — penyimpanan dan pencarian embedding menggunakan ChromaDB.

Perbaikan dari v1:
- Semua ChromaDB call di-wrap dalam run_in_executor agar tidak memblokir event loop.
  ChromaDB PersistentClient bersifat synchronous; memanggil langsung di `async def`
  akan membekukan seluruh event loop selama operasi berlangsung.
"""
from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Optional, List

import chromadb
from chromadb.config import Settings as ChromaSettings
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Antarmuka ChromaDB untuk menyimpan dan mencari embedding skripsi."""

    def __init__(self) -> None:
        self.client = chromadb.PersistentClient(
            path=settings.CHROMA_DB_PATH,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=settings.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "VectorStore siap — collection '%s' (%d embedding).",
            settings.COLLECTION_NAME,
            self.collection.count(),
        )

    # ── Internal helper ────────────────────────────────────────────────────────

    async def _run(self, fn, *args, **kwargs):
        """
        Jalankan fungsi synchronous ChromaDB di thread-pool executor
        agar tidak memblokir asyncio event loop.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(fn, *args, **kwargs))

    # ── Penulisan ──────────────────────────────────────────────────────────────

    async def upsert(
        self,
        skripsi_id: int,
        embedding: np.ndarray,
        metadata: dict,
    ) -> None:
        """Tambah atau perbarui satu embedding."""
        await self._run(
            self.collection.upsert,
            ids=[str(skripsi_id)],
            embeddings=[embedding.tolist()],
            metadatas=[metadata],
        )

    async def upsert_batch(
        self,
        skripsi_ids: List[int],
        embeddings: np.ndarray,
        metadatas: List[dict],
    ) -> None:
        """Tambah atau perbarui banyak embedding sekaligus."""
        await self._run(
            self.collection.upsert,
            ids=[str(sid) for sid in skripsi_ids],
            embeddings=embeddings.tolist(),
            metadatas=metadatas,
        )

    # ── Pembacaan ──────────────────────────────────────────────────────────────

    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        exclude_id: Optional[int] = None,
    ) -> List[dict]:
        """
        Cari `top_k` embedding paling mirip dengan `query_embedding`.
        Kembalikan list dict berisi id, similarity_score, dan metadata.
        """
        count = await self._run(self.collection.count)
        if count == 0:
            return []

        n_results = min(top_k + (1 if exclude_id else 0), count)

        results = await self._run(
            self.collection.query,
            query_embeddings=[query_embedding.tolist()],
            n_results=n_results,
            include=["metadatas", "distances"],
        )

        output: List[dict] = []
        for i, doc_id in enumerate(results["ids"][0]):
            if exclude_id and int(doc_id) == exclude_id:
                continue

            distance   = results["distances"][0][i]
            similarity = round(1.0 - distance, 4)
            metadata   = results["metadatas"][0][i]

            output.append({
                "id": int(doc_id),
                "similarity_score": similarity,
                **metadata,
            })

            if len(output) >= top_k:
                break

        return output

    # ── Penghapusan ────────────────────────────────────────────────────────────

    async def delete(self, skripsi_id: int) -> None:
        """Hapus embedding berdasarkan id."""
        await self._run(self.collection.delete, ids=[str(skripsi_id)])

    # ── Statistik ──────────────────────────────────────────────────────────────

    async def count(self) -> int:
        """Jumlah embedding yang tersimpan."""
        return await self._run(self.collection.count)
