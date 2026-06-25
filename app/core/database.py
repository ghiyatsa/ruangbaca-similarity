"""
Inisialisasi database SQLite dihapus.
FastAPI ini 100% stateless dan tidak membutuhkan engine relational DB.
"""

async def init_db() -> None:
    """No-op: Database SQL lokal dihapus."""
    pass
