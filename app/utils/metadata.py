"""
Helpers umum yang dipakai di beberapa router.
"""
from app.schemas.skripsi import SyncItem


def build_metadata(source: SyncItem) -> dict:
    """
    Simpan metadata minimum tetapi kaya untuk kebutuhan laporan statistik.
    """
    return {
        "skripsi_id": source.skripsi_id,
        "tahun": source.tahun if source.tahun else 0,
        "program_studi": source.program_studi if source.program_studi else "Tidak Diketahui",
    }

