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
from typing import Optional, List, Union

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
        document: Optional[str] = None,
    ) -> None:
        """Tambah atau perbarui satu embedding."""
        kwargs = {
            "ids": [str(skripsi_id)],
            "embeddings": [embedding.tolist()],
            "metadatas": [metadata],
        }
        if document is not None:
            kwargs["documents"] = [document]
        await self._run(
            self.collection.upsert,
            **kwargs
        )

    async def upsert_batch(
        self,
        skripsi_ids: List[int],
        embeddings: np.ndarray,
        metadatas: List[dict],
        documents: Optional[List[str]] = None,
    ) -> None:
        """Tambah atau perbarui banyak embedding sekaligus."""
        kwargs = {
            "ids": [str(sid) for sid in skripsi_ids],
            "embeddings": embeddings.tolist(),
            "metadatas": metadatas,
        }
        if documents is not None:
            kwargs["documents"] = documents
        await self._run(
            self.collection.upsert,
            **kwargs
        )

    # ── Pembacaan ──────────────────────────────────────────────────────────────

    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        exclude_id: Optional[int] = None,
        document_type: Optional[str] = None,
    ) -> List[dict]:
        """
        Cari `top_k` embedding paling mirip dengan `query_embedding`.
        Kembalikan list dict berisi id, similarity_score, dan metadata.
        """
        count = await self._run(self.collection.count)
        if count == 0:
            return []

        n_results = min(top_k + (1 if exclude_id else 0), count)

        query_params = {
            "query_embeddings": [query_embedding.tolist()],
            "n_results": n_results,
            "include": ["metadatas", "distances"],
        }
        if document_type:
            query_params["where"] = {"document_type": document_type}

        results = await self._run(
            self.collection.query,
            **query_params
        )

        output: List[dict] = []
        for i, doc_id in enumerate(results["ids"][0]):
            if exclude_id and doc_id == str(exclude_id):
                continue

            distance   = results["distances"][0][i]
            similarity = round(1.0 - distance, 4)
            metadata   = results["metadatas"][0][i]

            output.append({
                "id": doc_id,
                "similarity_score": similarity,
                **metadata,
            })

            if len(output) >= top_k:
                break

        return output

    # ── Penghapusan ────────────────────────────────────────────────────────────

    async def indexed_ids(self, limit: int = 500, offset: int = 0) -> List[str]:
        """Ambil daftar ID dokumen yang saat ini tersimpan di vector store."""
        results = await self._run(
            self.collection.get,
            limit=limit,
            offset=offset,
        )

        return [str(doc_id) for doc_id in results.get("ids", [])]

    async def delete(self, skripsi_id: Union[int, str]) -> None:
        """Hapus embedding berdasarkan id."""
        await self._run(self.collection.delete, ids=[str(skripsi_id)])

    async def reset(self) -> None:
        """Hapus seluruh collection lalu buat ulang dengan konfigurasi yang sama."""
        await self._run(self.client.delete_collection, settings.COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=settings.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("VectorStore direset — collection '%s' kosong.", settings.COLLECTION_NAME)

    # ── Statistik ──────────────────────────────────────────────────────────────

    async def count(self) -> int:
        """Jumlah embedding yang tersimpan."""
        return await self._run(self.collection.count)

    async def fetch_all_titles(self) -> List[str]:
        """Ambil semua judul dari ChromaDB (baik dari documents atau metadatas)."""
        count = await self.count()
        if count == 0:
            return []
        
        # Ambil semua data. Untuk skalabilitas, kita batasi sampai 50.000 data.
        results = await self._run(
            self.collection.get,
            limit=50000,
            include=["documents", "metadatas"]
        )
        
        titles = []
        # Coba ambil dari documents dulu
        if results.get("documents"):
            titles = [doc for doc in results["documents"] if doc]
        
        # Jika kosong atau tidak lengkap, fallback ke metadatas
        if not titles and results.get("metadatas"):
            for meta in results["metadatas"]:
                if meta and "judul" in meta:
                    titles.append(meta["judul"])
                    
        return titles
