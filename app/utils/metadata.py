"""
Helpers umum yang dipakai di beberapa router.
"""
from app.schemas.skripsi import SyncItem


def build_metadata(source: SyncItem) -> dict:
    """
    Simpan metadata minimum agar service ini tetap vector-only.
    """
    return {
        "skripsi_id": source.skripsi_id,
    }
