"""
Helpers umum yang dipakai di beberapa router.
"""
from app.models.skripsi import Skripsi
from app.schemas.skripsi import SyncItem


def build_metadata(source: "Skripsi | SyncItem") -> dict:
    """
    Buat dict metadata yang disimpan bersama embedding di ChromaDB.

    Metadata ini digunakan saat menampilkan hasil pencarian,
    sehingga hanya field yang relevan untuk ditampilkan yang disimpan.
    """
    if isinstance(source, SyncItem):
        return {
            "judul":           source.judul or "",
            "nama_mahasiswa":  source.nama_mahasiswa or "",
            "program_studi":   source.program_studi or "",
            "tahun":           source.tahun or 0,
            "nim":             source.nim or "",
            "laravel_id":      source.laravel_id,
        }

    # SQLAlchemy Skripsi model
    return {
        "judul":           source.judul or "",
        "nama_mahasiswa":  source.nama_mahasiswa or "",
        "program_studi":   source.program_studi or "",
        "tahun":           source.tahun or 0,
        "nim":             source.nim or "",
        "laravel_id":      source.laravel_id or 0,
    }
