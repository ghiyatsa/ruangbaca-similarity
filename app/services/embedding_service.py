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

    @staticmethod
    def _resolve_weights(
        bobot_judul: Optional[float] = None,
        bobot_abstrak: Optional[float] = None,
        bobot_kata_kunci: Optional[float] = None,
    ) -> tuple[float, float, float]:
        weights = [
            settings.WEIGHT_JUDUL if bobot_judul is None else float(bobot_judul),
            settings.WEIGHT_ABSTRAK if bobot_abstrak is None else float(bobot_abstrak),
            settings.WEIGHT_KATA_KUNCI if bobot_kata_kunci is None else float(bobot_kata_kunci),
        ]
        weights = [max(weight, 0.0) for weight in weights]
        total = sum(weights)

        if total <= 1e-9:
            defaults = [
                max(float(settings.WEIGHT_JUDUL), 0.0),
                max(float(settings.WEIGHT_ABSTRAK), 0.0),
                max(float(settings.WEIGHT_KATA_KUNCI), 0.0),
            ]
            total = sum(defaults)

            if total <= 1e-9:
                return 1.0, 0.0, 0.0

            return tuple(weight / total for weight in defaults)

        return tuple(weight / total for weight in weights)

    def clean_title(self, title: str) -> str:
        """
        Membersihkan judul dari stopwords dan boilerplate akademik
        agar perbandingan semantik terfokus pada konten substantif.
        """
        if not title:
            return ""
        
        # Lowercase
        text = title.lower()
        
        # Gabungkan istilah teknis bertanda hubung/garis miring/titik (misal k-means -> kmeans, ui/ux -> uiux, c4.5 -> c45)
        import re
        text = re.sub(r'\b([a-z0-9]+)[-/.](([a-z0-9]+)\b)?', r'\1\3', text)
        
        # Hapus karakter non-alfanumerik lainnya (pertahankan huruf dan angka)
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        
        # Daftar kata penghubung dan boilerplate akademik yang diabaikan
        stopwords = {
            # Bahasa Indonesia
            'dan', 'yang', 'untuk', 'pada', 'dengan', 'dari', 'ke', 'di', 'ini', 'itu', 'atau',
            'sebagai', 'dalam', 'tentang', 'oleh', 'adalah', 'adapun', 'serta', 'sebuah', 'ia', 'juga',
            # Boilerplate akademik
            'rancang', 'bangun', 'sistem', 'aplikasi', 'metode', 'studi', 'kasus', 'algoritma',
            'perancangan', 'pembuatan', 'penerapan', 'berbasis', 'menggunakan', 'analisis', 
            'implementasi', 'uji', 'kinerja', 'evaluasi', 'pengembangan', 'model', 'rancangan', 
            'prototipe', 'prototype', 'berbasiskan', 'mengimplementasikan', 'menganalisis', 'berupa',
            'laporan', 'tugas', 'akhir', 'skripsi', 'kerja', 'praktek', 'praktik', 'kp',
            # Bahasa Inggris
            'of', 'the', 'and', 'in', 'on', 'for', 'with', 'a', 'an', 'to', 'based', 'using', 'system'
        }
        
        words = text.split()
        # Ambil dynamic_stopwords jika ada, jika tidak default ke set kosong
        dynamic_stopwords = getattr(self, "dynamic_stopwords", set())
        all_stopwords = stopwords.union(dynamic_stopwords)
        filtered = [w for w in words if w not in all_stopwords and len(w) >= 3]
        
        # Jika hasil filter kosong (misal judul sangat pendek / semua kata adalah stopwords), 
        # kembalikan teks asli agar tidak menghasilkan embedding kosong.
        if not filtered:
            return title.strip()
            
        return ' '.join(filtered)

    async def update_dynamic_stopwords(self, vector_store: "VectorStore", threshold: Optional[float] = None) -> None:
        """
        Hitung frekuensi kata di seluruh dokumen dan tentukan kata yang terlalu umum
        sebagai dynamic stopwords secara otomatis.
        """
        try:
            if threshold is None:
                threshold = settings.DYNAMIC_STOPWORDS_THRESHOLD

            titles = await vector_store.fetch_all_titles()
            if not titles:
                self.dynamic_stopwords = set()
                return

            import re
            from collections import Counter

            def _calculate_df():
                word_counts = Counter()
                for title in titles:
                    # Ambil kata unik per dokumen untuk menghitung Document Frequency (DF)
                    words = set(re.findall(r'[a-z0-9]{3,}', title.lower()))
                    for w in words:
                        word_counts[w] += 1
                return word_counts

            loop = asyncio.get_running_loop()
            word_counts = await loop.run_in_executor(None, _calculate_df)
            total_docs = len(titles)

            new_dynamic = set()
            for word, count in word_counts.items():
                df = count / total_docs
                if df >= threshold:
                    new_dynamic.add(word)

            self.dynamic_stopwords = new_dynamic
            logger.info(
                "Dynamic stopwords diperbarui: %d kata terdeteksi (threshold=%.2f, total_docs=%d). Kata umum: %s",
                len(new_dynamic),
                threshold,
                total_docs,
                list(new_dynamic)[:15]
            )
        except Exception as exc:
            logger.exception("Gagal memperbarui dynamic stopwords: %s", exc)

    async def encode_for_index(
        self,
        judul: str,
        abstrak: Optional[str] = None,
        kata_kunci: Optional[str] = None,
        bobot_judul: Optional[float] = None,
        bobot_abstrak: Optional[float] = None,
        bobot_kata_kunci: Optional[float] = None,
    ) -> np.ndarray:
        """
        Encode skripsi dengan membobotkan judul, abstrak, dan kata kunci.
        Masing-masing bagian di-encode terpisah lalu dijumlahkan secara berbobot.
        """
        if not self.is_loaded:
            await self.load_model()

        # 1. Encode bagian-bagian
        weight_judul, weight_abstrak, weight_kata_kunci = self._resolve_weights(
            bobot_judul=bobot_judul,
            bobot_abstrak=bobot_abstrak,
            bobot_kata_kunci=bobot_kata_kunci,
        )
        v_judul = await self._encode_single(self.clean_title(judul))

        combined_v = v_judul * weight_judul

        if abstrak:
            clean_abstrak = abstrak.strip()[: settings.ABSTRAK_MAX_CHARS]
            if clean_abstrak:
                v_abstrak = await self._encode_single(clean_abstrak)
                combined_v += v_abstrak * weight_abstrak

        if kata_kunci:
            clean_kk = kata_kunci.strip()
            if clean_kk:
                v_kk = await self._encode_single(clean_kk)
                combined_v += v_kk * weight_kata_kunci

        # 2. Re-normalize (penting untuk cosine similarity via dot product)
        norm = np.linalg.norm(combined_v)
        if norm > 1e-9:
            combined_v = combined_v / norm

        return combined_v

    async def encode_for_query(self, judul: str) -> np.ndarray:
        """Query selalu menggunakan judul saja."""
        if not self.is_loaded:
            await self.load_model()
        return await self._encode_single(self.clean_title(judul))

    async def encode_batch_for_index(self, items: List[tuple]) -> np.ndarray:
        """
        Encode banyak skripsi sekaligus dengan pembobotan.
        Efisiensi ditingkatkan dengan melakukan batch inference untuk semua bagian.
        """
        if not self.is_loaded:
            await self.load_model()

        # 1. Kumpulkan semua teks unik untuk di-encode (mengurangi redundansi)
        # Format: [(judul, abstrak, kata_kunci, bobot_judul, bobot_abstrak, bobot_kata_kunci), ...]
        all_texts = []
        mapping = [] # Untuk melacak index mana milik skripsi mana

        for j, a, k, weight_j, weight_a, weight_k in items:
            # Kita simpan index untuk rekonstruksi nanti
            idx_judul = len(all_texts)
            all_texts.append(self.clean_title(j))
            
            idx_abstrak = -1
            if a:
                clean_a = a.strip()[: settings.ABSTRAK_MAX_CHARS]
                if clean_a:
                    idx_abstrak = len(all_texts)
                    all_texts.append(clean_a)
            
            idx_kk = -1
            if k:
                clean_k = k.strip()
                if clean_k:
                    idx_kk = len(all_texts)
                    all_texts.append(clean_k)
            
            mapping.append((idx_judul, idx_abstrak, idx_kk, *self._resolve_weights(
                bobot_judul=weight_j,
                bobot_abstrak=weight_a,
                bobot_kata_kunci=weight_k,
            )))
        # 2. Batch encode semua teks
        all_embeddings = await self._encode_batch(all_texts)

        # 3. Rekonstruksi vektor berbobot
        results = []
        for idx_j, idx_a, idx_k, weight_j, weight_a, weight_k in mapping:
            v_combined = all_embeddings[idx_j] * weight_j

            if idx_a != -1:
                v_combined += all_embeddings[idx_a] * weight_a

            if idx_k != -1:
                v_combined += all_embeddings[idx_k] * weight_k

            # Normalisasi
            norm = np.linalg.norm(v_combined)
            if norm > 1e-9:
                v_combined = v_combined / norm
            
            results.append(v_combined)

        return np.array(results)

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
