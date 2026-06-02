"""
Pydantic schemas untuk validasi request / response.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


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
    judul: str = Field(..., min_length=5, max_length=500, description="Judul skripsi")
    abstrak: Optional[str] = Field(None, description="Abstrak skripsi")
    kata_kunci: Optional[str] = Field(None, description="Kata kunci dipisah koma")
    tahun: Optional[int] = Field(None, ge=1990, le=2100)
    program_studi: Optional[str] = Field(None, description="Program studi sumber")
    nim: Optional[str] = Field(None, description="NIM mahasiswa")
    nama_mahasiswa: Optional[str] = Field(None, description="Nama mahasiswa")
    bobot_judul: Optional[float] = Field(None, ge=0, description="Bobot embedding bagian judul")
    bobot_abstrak: Optional[float] = Field(None, ge=0, description="Bobot embedding bagian abstrak")
    bobot_kata_kunci: Optional[float] = Field(None, ge=0, description="Bobot embedding bagian kata kunci")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "skripsi_id": 123,
                "judul": "Sistem Rekomendasi Wisata Menggunakan Metode KNN",
                "abstrak": "Penelitian ini membahas sistem rekomendasi wisata berbasis kemiripan preferensi pengguna.",
                "kata_kunci": "sistem rekomendasi, knn, wisata",
                "tahun": 2024,
                "program_studi": "Informatika",
                "nim": "2001700123",
                "nama_mahasiswa": "Alya Putri",
                "bobot_judul": 0.7,
                "bobot_abstrak": 0.2,
                "bobot_kata_kunci": 0.1,
            }
        },
    )


class BulkSyncRequest(BaseModel):
    """Payload bulk-sync dari perintah artisan `php artisan skripsi:sync`."""

    data: List[SyncItem]
    reset_index: bool = Field(
        False,
        description="Jika true, kosongkan vector index terlebih dahulu sebelum reindex penuh.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "data": [
                    {
                        "skripsi_id": 123,
                        "judul": "Sistem Rekomendasi Wisata Menggunakan Metode KNN",
                        "abstrak": "Penelitian ini membahas sistem rekomendasi wisata berbasis kemiripan preferensi pengguna.",
                        "kata_kunci": "sistem rekomendasi, knn, wisata",
                        "tahun": 2024,
                        "program_studi": "Informatika",
                        "nim": "2001700123",
                        "nama_mahasiswa": "Alya Putri",
                    }
                ],
                "reset_index": False,
            }
        },
    )


class SyncResponse(BaseModel):
    message: str
    skripsi_id: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Skripsi berhasil di-upsert",
                "skripsi_id": 123,
            }
        },
    )


class BulkSyncResponse(BaseModel):
    message: str
    status: str
    total_received: int
    job_id: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Menerima 100 item dan job sedang diproses.",
                "status": "accepted",
                "total_received": 100,
                "job_id": "2d8e8f5d-9d60-4f5c-9d06-7e5f5a2e8f11",
            }
        },
    )


class BulkSyncJobStatusResponse(BaseModel):
    job_id: str
    status: str
    total_received: int
    total_processed: int
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "2d8e8f5d-9d60-4f5c-9d06-7e5f5a2e8f11",
                "status": "completed",
                "total_received": 100,
                "total_processed": 100,
                "error_message": None,
                "created_at": "2026-05-17T12:34:56Z",
                "started_at": "2026-05-17T12:34:57Z",
                "completed_at": "2026-05-17T12:35:08Z",
            }
        },
    )


class IndexedIdsResponse(BaseModel):
    ids: List[int]
    total_indexed: int
    next_offset: Optional[int] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ids": [123, 124, 125],
                "total_indexed": 477,
                "next_offset": 500,
            }
        },
    )


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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "judul": "Sistem rekomendasi wisata berbasis web",
                "top_k": 5,
                "threshold": 0.75,
            }
        },
    )


class SimilarResult(BaseModel):
    id: int = Field(..., description="ID skripsi pada sistem sumber/Laravel")
    similarity_score: float = Field(..., description="Skor cosine similarity 0.0 - 1.0")
    similarity_persen: str = Field(..., description="Contoh: '87.2%'")
    level: str = Field(..., description="SANGAT TINGGI / TINGGI / SEDANG / RENDAH")


class SimilarityCheckResponse(BaseModel):
    query: Dict[str, Any]
    total_found: int
    results: List[SimilarResult]
    peringatan: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": {
                    "judul": "Sistem rekomendasi wisata berbasis web",
                },
                "total_found": 2,
                "results": [
                    {
                        "id": 123,
                        "similarity_score": 0.9211,
                        "similarity_persen": "92.11%",
                        "level": "SANGAT TINGGI",
                    },
                    {
                        "id": 98,
                        "similarity_score": 0.8412,
                        "similarity_persen": "84.12%",
                        "level": "TINGGI",
                    },
                ],
                "peringatan": "Ditemukan judul dengan kemiripan SANGAT TINGGI (92.11%). Pertimbangkan untuk merevisi judul atau topik penelitian Anda.",
            }
        },
    )
