"""
Definisi skema data Pydantic untuk validasi input dan output API.
Mencakup model untuk:
- Item sinkronisasi dokumen tunggal (SyncItem) dan massal (BulkSyncRequest).
- Response status sinkronisasi (SyncResponse, BulkSyncResponse, BulkSyncJobStatusResponse).
- Parameter deteksi kemiripan (SimilarityCheckRequest) dan hasilnya (SimilarResult, SimilarityCheckResponse).
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class SyncItem(BaseModel):
    """
    Satu item dokumen (Skripsi atau InternshipReport) yang dikirim dari Laravel.
    """

    document_id: str = Field(
        ...,
        description="ID unik dokumen (e.g. skripsi_123, internship_report_456)",
        validation_alias=AliasChoices("document_id", "skripsi_id", "laravel_id"),
    )
    document_type: str = Field(
        "skripsi",
        description="Tipe dokumen: skripsi atau internship_report",
        validation_alias=AliasChoices("document_type", "type"),
    )
    skripsi_id: Optional[int] = Field(
        None,
        description="ID integer asli (untuk backward compatibility)",
    )
    judul: str = Field(..., min_length=5, max_length=500, description="Judul dokumen")
    abstrak: Optional[str] = Field(None, description="Abstrak dokumen")
    kata_kunci: Optional[str] = Field(None, description="Kata kunci dipisah koma")
    tahun: Optional[int] = Field(None, ge=1990, le=2100)
    program_studi: Optional[str] = Field(None, description="Program studi")
    nim: Optional[str] = Field(None, description="NIM mahasiswa")
    nama_mahasiswa: Optional[str] = Field(None, description="Nama mahasiswa")
    bobot_judul: Optional[float] = Field(None, ge=0, description="Bobot embedding bagian judul")
    bobot_abstrak: Optional[float] = Field(None, ge=0, description="Bobot embedding bagian abstrak")
    bobot_kata_kunci: Optional[float] = Field(None, ge=0, description="Bobot embedding bagian kata kunci")

    @model_validator(mode="before")
    @classmethod
    def populate_document_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            doc_type = data.get("document_type") or data.get("type") or "skripsi"
            data["document_type"] = doc_type

            s_id = data.get("skripsi_id") or data.get("laravel_id")
            if s_id is not None:
                data["skripsi_id"] = int(s_id)

            doc_id = data.get("document_id")
            if not doc_id:
                if s_id is not None:
                    data["document_id"] = f"{doc_type}_{s_id}"
                else:
                    raise ValueError("Either document_id or skripsi_id must be provided")
            else:
                data["document_id"] = str(doc_id)
                if "_" in data["document_id"] and data.get("skripsi_id") is None:
                    parts = data["document_id"].split("_")
                    if parts[-1].isdigit():
                        data["skripsi_id"] = int(parts[-1])
        return data

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "document_id": "skripsi_123",
                "document_type": "skripsi",
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
    """Payload bulk-sync."""

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
                        "document_id": "skripsi_123",
                        "document_type": "skripsi",
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
    document_id: str
    skripsi_id: Optional[int] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Dokumen berhasil di-upsert",
                "document_id": "skripsi_123",
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


class SimilarityCheckRequest(BaseModel):
    """
    Request cek kemiripan.
    """

    judul: str = Field(..., min_length=5, description="Judul dokumen yang ingin dicek")
    top_k: int = Field(default=5, ge=1, le=20, description="Jumlah hasil teratas")
    threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Skor minimum kemiripan")
    document_type: Optional[str] = Field(None, description="Filter tipe dokumen: skripsi atau internship_report")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "judul": "Sistem rekomendasi wisata berbasis web",
                "top_k": 5,
                "threshold": 0.75,
                "document_type": "skripsi",
            }
        },
    )


class SimilarResult(BaseModel):
    id: str = Field(..., description="ID dokumen unik di vector store (e.g. skripsi_123)")
    document_id: int = Field(..., description="ID integer asli dari database sumber")
    document_type: str = Field(..., description="Tipe dokumen (e.g. skripsi, internship_report)")
    skripsi_id: Optional[int] = Field(None, description="Alias untuk backward compatibility")
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
                        "id": "skripsi_123",
                        "document_id": 123,
                        "document_type": "skripsi",
                        "skripsi_id": 123,
                        "similarity_score": 0.9211,
                        "similarity_persen": "92.11%",
                        "level": "SANGAT TINGGI",
                    },
                    {
                        "id": "internship_report_98",
                        "document_id": 98,
                        "document_type": "internship_report",
                        "skripsi_id": None,
                        "similarity_score": 0.8412,
                        "similarity_persen": "84.12%",
                        "level": "TINGGI",
                    },
                ],
                "peringatan": "Ditemukan judul dengan kemiripan SANGAT TINGGI (92.11%).",
            }
        },
    )
