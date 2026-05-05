"""
EmbeddingService - mengubah teks menjadi vector embedding.

Perbaikan dari v1:
- Ganti @alru_cache (tidak kompatibel dengan np.ndarray) -> cachetools.LRUCache
- Ganti asyncio.get_event_loop() -> asyncio.get_running_loop() (Python 3.10+)
- Tambah inference semaphore agar concurrent inference tidak menyebabkan OOM
- Thread-safe cache dengan threading.Lock
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import threading
from typing import List, Optional, Union

import numpy as np
from cachetools import LRUCache

from app.core.config import settings

logger = logging.getLogger(__name__)

# Opsional: Optimum untuk ONNX Runtime
try:
    from optimum.onnxruntime import ORTModelForFeatureExtraction
    from transformers import AutoTokenizer

    HAS_OPTIMUM = True
except ImportError:
    HAS_OPTIMUM = False


def _first_existing_path(candidates: List[str]) -> Optional[str]:
    """Kembalikan path lokal pertama yang benar-benar ada."""
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def _local_model_roots() -> List[str]:
    return [
        "./model",
        "./model_cache/model",
        "./model_cache/_st_cache",
    ]


def _onnx_file_candidates() -> List[str]:
    machine = platform.machine().lower()
    if "arm" in machine or "aarch" in machine:
        return [
            "onnx/model_qint8_arm64.onnx",
            "model.onnx",
        ]

    return [
        "onnx/model_quint8_avx2.onnx",
        "onnx/model_qint8_avx512_vnni.onnx",
        "onnx/model_qint8_avx512.onnx",
        "model.onnx",
    ]


class EmbeddingService:
    """
    Mengubah teks menjadi vector embedding.
    Mendukung ONNX (via Optimum) untuk performa maksimal di CPU,
    dengan fallback ke SentenceTransformer standar.
    """

    def __init__(self) -> None:
        self.model: Optional[Union["SentenceTransformer", "ORTModelForFeatureExtraction"]] = None
        self.tokenizer: Optional["AutoTokenizer"] = None
        self.is_onnx: bool = False
        self.is_loaded: bool = False

        # Thread-safe LRU cache - ganti @alru_cache yang bermasalah dengan np.ndarray
        self._cache: LRUCache[str, np.ndarray] = LRUCache(maxsize=1024)
        self._cache_lock = threading.Lock()

    async def load_model(self) -> None:
        """Muat model secara async. Mencoba ONNX dulu, lalu fallback ke ST."""
        if self.is_loaded:
            return

        loop = asyncio.get_running_loop()

        if HAS_OPTIMUM:
            for model_root in _local_model_roots():
                if not os.path.exists(model_root):
                    continue

                for onnx_file in _onnx_file_candidates():
                    onnx_full_path = os.path.join(model_root, onnx_file)
                    if not os.path.exists(onnx_full_path):
                        continue

                    logger.info(
                        "Menggunakan model ONNX dari: %s (%s)",
                        model_root,
                        onnx_file,
                    )
                    try:
                        self.model = await loop.run_in_executor(
                            None,
                            lambda root=model_root, file_name=onnx_file: (
                                ORTModelForFeatureExtraction.from_pretrained(
                                    root,
                                    file_name=file_name,
                                )
                            ),
                        )
                        self.tokenizer = await loop.run_in_executor(
                            None,
                            lambda root=model_root: AutoTokenizer.from_pretrained(root),
                        )
                        self.is_onnx = True
                        self.is_loaded = True
                        logger.info("Model ONNX berhasil dimuat.")
                        return
                    except Exception as exc:
                        logger.warning(
                            "Gagal memuat ONNX dari %s (%s): %s",
                            model_root,
                            onnx_file,
                            exc,
                        )

        # Fallback ke SentenceTransformer
        from sentence_transformers import SentenceTransformer

        local_model_path = _first_existing_path(_local_model_roots())
        if local_model_path:
            logger.info("Menggunakan model lokal (baked-in) dari: %s", local_model_path)
            load_path = local_model_path
        else:
            logger.info("Menggunakan SentenceTransformer: %s", settings.MODEL_NAME)
            load_path = settings.MODEL_NAME

        self.model = await loop.run_in_executor(
            None,
            lambda: SentenceTransformer(load_path),
        )
        self.is_onnx = False
        self.is_loaded = True
        logger.info("Model SentenceTransformer berhasil dimuat.")

    @staticmethod
    def build_index_text(
        judul: str,
        abstrak: Optional[str] = None,
        kata_kunci: Optional[str] = None,
    ) -> str:
        parts = [judul.strip()]
        if abstrak:
            parts.append(abstrak.strip()[: settings.ABSTRAK_MAX_CHARS])
        if kata_kunci:
            parts.append(kata_kunci.strip())
        return " | ".join(parts)

    @staticmethod
    def build_query_text(judul: str) -> str:
        return judul.strip()

    async def encode_for_index(
        self,
        judul: str,
        abstrak: Optional[str] = None,
        kata_kunci: Optional[str] = None,
    ) -> np.ndarray:
        if not self.is_loaded:
            await self.load_model()
        text = self.build_index_text(judul, abstrak, kata_kunci)
        return await self._encode_single(text)

    async def encode_for_query(self, judul: str) -> np.ndarray:
        if not self.is_loaded:
            await self.load_model()
        text = self.build_query_text(judul)
        return await self._encode_single(text)

    async def encode_batch_for_index(self, items: List[tuple]) -> np.ndarray:
        if not self.is_loaded:
            await self.load_model()
        texts = [self.build_index_text(j, a, k) for j, a, k in items]
        return await self._encode_batch(texts)

    async def _encode_single(self, text: str) -> np.ndarray:
        """Encode satu teks dengan cache + semaphore."""
        with self._cache_lock:
            if text in self._cache:
                return self._cache[text]

        from app.core.limiter import get_inference_semaphore

        async with get_inference_semaphore():
            with self._cache_lock:
                if text in self._cache:
                    return self._cache[text]

            loop = asyncio.get_running_loop()
            if self.is_onnx:
                result = await loop.run_in_executor(
                    None,
                    lambda: self._onnx_encode([text])[0],
                )
            else:
                result = await loop.run_in_executor(
                    None,
                    lambda: self.model.encode(text, normalize_embeddings=True),
                )

        with self._cache_lock:
            self._cache[text] = result
        return result

    async def _encode_batch(self, texts: List[str]) -> np.ndarray:
        """Encode batch teks - semaphore diterapkan, tanpa cache individual."""
        from app.core.limiter import get_inference_semaphore

        async with get_inference_semaphore():
            loop = asyncio.get_running_loop()
            if self.is_onnx:
                return await loop.run_in_executor(
                    None,
                    lambda: self._onnx_encode(texts),
                )
            return await loop.run_in_executor(
                None,
                lambda: self.model.encode(
                    texts,
                    normalize_embeddings=True,
                    batch_size=32,
                ),
            )

    def _onnx_encode(self, texts: List[str]) -> np.ndarray:
        """Inferensi ONNX: Tokenize -> Model -> Mean Pooling -> L2 Normalize."""
        encoded_input = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        model_output = self.model(**encoded_input)

        token_embeddings = model_output.last_hidden_state
        attention_mask = encoded_input["attention_mask"]
        input_mask_expanded = (
            attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        )

        sum_embeddings = (token_embeddings * input_mask_expanded).sum(1)
        sum_mask = input_mask_expanded.sum(1).clamp(min=1e-9)
        embeddings = (sum_embeddings / sum_mask).detach().cpu().numpy()

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings / norms

    def cosine_similarity(self, vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """Cosine similarity untuk dua vektor ternormalisasi (dot product)."""
        return float(np.dot(vec_a, vec_b))

    def cache_info(self) -> dict:
        """Statistik cache untuk monitoring."""
        with self._cache_lock:
            return {
                "size": len(self._cache),
                "maxsize": self._cache.maxsize,
                "currsize": self._cache.currsize,
            }
