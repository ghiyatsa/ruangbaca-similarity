"""
Konfigurasi pytest — shared fixtures dan path setup.

Fixture di sini membangun aplikasi FastAPI uji dengan router asli (prefix +
dependency auth yang sama seperti main.py) namun dengan embedding service dan
vector store palsu, sehingga test tidak memuat model ONNX/Transformer maupun
menyentuh ChromaDB di disk.
"""
import os
import sys

import numpy as np
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class FakeEmbeddingService:
    """Pengganti EmbeddingService: deterministik, tanpa model berat."""

    def __init__(self) -> None:
        self.is_loaded = True
        self.is_onnx = False
        self.update_calls = 0

    def clean_title(self, text: str) -> str:
        return text.lower().strip()

    async def encode_for_query(self, judul: str) -> np.ndarray:
        return np.array([1.0, 0.0, 0.0])

    async def encode_for_index(self, **_kwargs) -> np.ndarray:
        return np.array([0.0, 1.0, 0.0])

    async def encode_batch_for_index(self, items) -> np.ndarray:
        return np.array([[0.0, 1.0, 0.0] for _ in items])

    def cosine_similarity(self, _vec_a, _vec_b) -> float:
        return 0.8

    async def update_dynamic_stopwords(self, _vector_store) -> None:
        self.update_calls += 1


class _FakeCollection:
    """Tiruan koleksi ChromaDB untuk endpoint /stats."""

    def __init__(self, metadatas=None) -> None:
        self._metadatas = metadatas or []

    def get(self, **_kwargs) -> dict:
        return {"metadatas": self._metadatas, "ids": []}

    def count(self) -> int:
        return len(self._metadatas)


class FakeVectorStore:
    """Pengganti VectorStore: mencatat panggilan, mengembalikan data terkendali."""

    def __init__(self, count: int = 0, search_results=None, metadatas=None) -> None:
        self._count = count
        self._search_results = search_results or []
        self.collection = _FakeCollection(metadatas)
        self.upserts: list = []
        self.deleted: list = []
        self.reset_called = False

    async def _run(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def count(self) -> int:
        return self._count

    async def search(self, query_embedding, top_k=5, exclude_id=None, document_type=None):
        return self._search_results[:top_k]

    async def upsert(self, skripsi_id, embedding, metadata, document=None) -> None:
        self.upserts.append({"id": skripsi_id, "metadata": metadata, "document": document})

    async def upsert_batch(self, skripsi_ids, embeddings, metadatas, documents=None) -> None:
        self.upserts.append({"ids": skripsi_ids, "metadatas": metadatas})

    async def delete(self, skripsi_id) -> None:
        self.deleted.append(skripsi_id)

    async def reset(self) -> None:
        self.reset_called = True

    async def fetch_all_titles(self):
        return []


@pytest.fixture(autouse=True)
def _reset_shared_state():
    """Bersihkan rate limiter dan repo job in-memory antar test."""
    from app.core.limiter import limiter
    from app.repositories import sync_job_repo

    limiter.reset()
    sync_job_repo._jobs.clear()

    yield

    sync_job_repo._jobs.clear()


@pytest.fixture
def fake_embedding() -> FakeEmbeddingService:
    return FakeEmbeddingService()


@pytest.fixture
def fake_store() -> FakeVectorStore:
    return FakeVectorStore()


def build_test_app(embedding, store) -> FastAPI:
    """Bangun app uji dengan wiring router identik dengan main.py."""
    from app.api import similarity, sync
    from app.api.deps import verify_sync_token
    from app.core.config import settings
    from app.core.limiter import limiter

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.state.embedding_service = embedding
    app.state.vector_store = store

    app.include_router(
        similarity.router,
        prefix=f"{settings.API_V1_STR}/similarity",
        dependencies=[Depends(verify_sync_token)],
    )
    app.include_router(
        sync.router,
        prefix=f"{settings.API_V1_STR}/sync",
    )

    return app


@pytest.fixture
def client(fake_embedding, fake_store) -> TestClient:
    return TestClient(build_test_app(fake_embedding, fake_store))


@pytest.fixture
def auth_headers() -> dict:
    from app.core.config import settings

    return {"X-Similarity-Api-Secret": settings.SYNC_SECRET}
