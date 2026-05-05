"""
Pydantic schemas untuk validasi request / response.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class SkripsiResponse(BaseModel):
    """Data skripsi yang dikembalikan oleh endpoint GET."""

    id: int
    skripsi_id: Optional[int] = None
    judul: str
    abstrak: Optional[str] = None
    kata_kunci: Optional[str] = None
    tahun: Optional[int] = None
    program_studi: Optional[str] = None
    nim: Optional[str] = None
    nama_mahasiswa: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SyncItem(BaseModel):
    """
    Satu item skripsi yang dikirim dari Laravel Observer atau Artisan Command.

    `laravel_id` masih diterima sebagai alias sementara agar rollout dari
    integrasi lama tidak langsung putus.
    """

    skripsi_id: int = Field(
        ...,
        description="Primary key dari database sumber/Laravel",
        validation_alias=AliasChoices("skripsi_id", "laravel_id"),
    )
    judul: str = Field(..., min_length=5, max_length=500)
    abstrak: Optional[str] = None
    kata_kunci: Optional[str] = None
    tahun: Optional[int] = Field(None, ge=1990, le=2100)
    program_studi: Optional[str] = None
    nim: Optional[str] = None
    nama_mahasiswa: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class BulkSyncRequest(BaseModel):
    """Payload bulk-sync dari perintah artisan `php artisan skripsi:sync`."""

    data: List[SyncItem]


class SyncResponse(BaseModel):
    message: str
    skripsi_id: int
    local_id: int


class BulkSyncResponse(BaseModel):
    message: str
    status: str
    total_received: int


class SimilarityCheckRequest(BaseModel):
    """
    Request cek kemiripan.

    Hanya `judul` yang wajib diisi. Saat query, sistem akan membuat embedding
    dari judul saja lalu membandingkannya dengan embedding database yang sudah
    mencakup judul + abstrak + kata kunci.
    """

    judul: str = Field(..., min_length=5, description="Judul skripsi yang ingin dicek")
    top_k: int = Field(default=5, ge=1, le=20, description="Jumlah hasil teratas")
    threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Skor minimum kemiripan")


class SimilarResult(BaseModel):
    id: int
    skripsi_id: Optional[int] = None
    judul: str
    nama_mahasiswa: Optional[str] = None
    program_studi: Optional[str] = None
    tahun: Optional[int] = None
    similarity_score: float = Field(..., description="Skor 0.0 - 1.0")
    similarity_persen: str = Field(..., description="Contoh: '87.2%'")
    level: str = Field(..., description="SANGAT TINGGI / TINGGI / SEDANG / RENDAH")


class SimilarityCheckResponse(BaseModel):
    query: Dict[str, Any]
    total_found: int
    results: List[SimilarResult]
    peringatan: Optional[str] = None
