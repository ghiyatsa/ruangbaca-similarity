"""
Konfigurasi aplikasi via pydantic-settings.
Semua nilai di-load dari environment variable / file .env secara otomatis
dengan validasi tipe yang ketat saat startup.
"""
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Metadata ───────────────────────────────────────────────────────────────
    PROJECT_NAME: str = "Skripsi Similarity API"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"
    PORT: int = 8181

    # ── Database — SQLite only ─────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./skripsi.db"

    # ── ChromaDB (vector store) ─────────────────────────────────────────────────
    CHROMA_DB_PATH: str = "./chroma_db"
    COLLECTION_NAME: str = "skripsi_embeddings"

    # ── Sentence-Transformers model ─────────────────────────────────────────────
    MODEL_NAME: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    ABSTRAK_MAX_CHARS: int = 300

    # ── CORS ────────────────────────────────────────────────────────────────────
    # Gunakan str agar pydantic-settings tidak mencoba JSON-decode nilai dari .env.
    # Gunakan property `allowed_origins_list` untuk mendapat List[str].
    ALLOWED_ORIGINS: str = "http://localhost:8000"

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse ALLOWED_ORIGINS yang dipisah koma menjadi list."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # ── Keamanan sync ───────────────────────────────────────────────────────────
    # Wajib ada di .env — aplikasi GAGAL START jika tidak di-set atau masih default.
    SYNC_SECRET: str = Field(..., min_length=16)

    @field_validator("SYNC_SECRET")
    @classmethod
    def secret_must_not_be_default(cls, v: str) -> str:
        if v.lower() in {"changeme-secret-token", "changeme", "secret", ""}:
            raise ValueError(
                "SYNC_SECRET harus diganti dari nilai default! "
                "Gunakan: openssl rand -hex 32"
            )
        return v

    # ── Concurrency control ─────────────────────────────────────────────────────
    # Batasi concurrent ML inference agar tidak OOM
    INFERENCE_CONCURRENCY: int = Field(default=4, ge=1, le=32)
    # Ukuran chunk untuk bulk-upsert
    BULK_SYNC_CHUNK_SIZE: int = Field(default=100, ge=10, le=1000)

    # ── Logging ─────────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── Offline mode (untuk Docker — model sudah di-bake ke image) ──────────────
    HF_HUB_OFFLINE: int = Field(default=0)
    TRANSFORMERS_OFFLINE: int = Field(default=0)


settings = Settings()
