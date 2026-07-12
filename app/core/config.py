"""
Manajemen konfigurasi aplikasi menggunakan pustaka pydantic-settings.
Seluruh nilai konfigurasi dimuat secara otomatis dari variabel lingkungan atau berkas .env
dengan validasi tipe data yang ketat pada saat aplikasi dijalankan.
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

    PROJECT_NAME: str = "RuangBaca Similarity API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    PORT: int = 8181

    CHROMA_DB_PATH: str = "./chroma_db"
    COLLECTION_NAME: str = "ruangbaca_embeddings"

    MODEL_NAME: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    ABSTRAK_MAX_CHARS: int = 300
    DYNAMIC_STOPWORDS_THRESHOLD: float = 0.15

    WEIGHT_JUDUL: float = 0.7
    WEIGHT_ABSTRAK: float = 0.2
    WEIGHT_KATA_KUNCI: float = 0.1

    HYBRID_SEMANTIC_WEIGHT: float = 0.7
    HYBRID_LEXICAL_WEIGHT: float = 0.3

    ALLOWED_ORIGINS: str = "http://localhost:8000"

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse ALLOWED_ORIGINS yang dipisah koma menjadi list."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

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

    INFERENCE_CONCURRENCY: int = Field(default=4, ge=1, le=32)
    BULK_SYNC_CHUNK_SIZE: int = Field(default=100, ge=10, le=1000)

    LOG_LEVEL: str = "INFO"

    HF_HUB_OFFLINE: int = Field(default=0)
    TRANSFORMERS_OFFLINE: int = Field(default=0)


settings = Settings()
