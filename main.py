"""
Entry point FastAPI untuk Skripsi Similarity API.
"""
from contextlib import asynccontextmanager
import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import similarity, skripsi, sync
from app.core.config import settings
from app.core.database import init_db
from app.core.limiter import limiter
from app.core.logging_config import setup_logging
from app.services.embedding_service import EmbeddingService
from app.services.vector_store import VectorStore

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

embedding_service = EmbeddingService()
vector_store = VectorStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: muat model dan inisialisasi DB. Shutdown: cleanup."""
    logger.info("Memuat model embedding: %s ...", settings.MODEL_NAME)
    await embedding_service.load_model()
    logger.info("Model berhasil dimuat.")

    logger.info("Menginisialisasi database ...")
    await init_db()
    logger.info("Database siap.")

    app.state.embedding_service = embedding_service
    app.state.vector_store = vector_store

    yield

    logger.info("Service ditutup.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "API deteksi kemiripan judul skripsi menggunakan Sentence Transformers dan ChromaDB.\n\n"
        "Pengguna cukup mengirimkan judul saja; sistem akan membandingkan dengan embedding "
        "database yang sudah mencakup abstrak dan kata kunci."
    ),
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    max_age=600,
)

app.include_router(
    similarity.router,
    prefix=f"{settings.API_V1_STR}/similarity",
    tags=["Similarity"],
)
app.include_router(
    skripsi.router,
    prefix=f"{settings.API_V1_STR}/skripsi",
    tags=["Skripsi"],
)
app.include_router(
    sync.router,
    prefix=f"{settings.API_V1_STR}/sync",
    tags=["Sync (Laravel)"],
)


@app.get("/", tags=["Meta"])
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health", tags=["Meta"])
async def health_check():
    total = await vector_store.count()
    cache = embedding_service.cache_info()
    return {
        "status": "healthy",
        "model_loaded": embedding_service.is_loaded,
        "model_name": settings.MODEL_NAME,
        "model_backend": "onnx" if embedding_service.is_onnx else "sentence-transformers",
        "total_indexed": total,
        "embedding_cache": cache,
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
