"""
Helper untuk ekstraksi dan konstruksi metadata dari dokumen akademik (SyncItem).
Digunakan untuk standardisasi metadata yang disimpan ke dalam vector store.
"""
from app.schemas.document import SyncItem


def build_metadata(source: SyncItem) -> dict:
    """
    Simpan metadata minimum tetapi kaya untuk kebutuhan laporan statistik.
    """
    return {
        "document_id": source.document_id,
        "document_type": source.document_type,
        "skripsi_id": source.skripsi_id,
        "tahun": source.tahun if source.tahun else 0,
        "program_studi": source.program_studi if source.program_studi else "Tidak Diketahui",
        "judul": source.judul,
    }

