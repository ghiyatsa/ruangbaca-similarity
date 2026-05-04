"""
SQLAlchemy model untuk tabel `skripsi`.

Kolom `laravel_id` digunakan sebagai foreign-key logis ke tabel skripsi di
aplikasi Laravel utama. Ini memungkinkan sinkronisasi dua arah tanpa harus
menyamakan primary-key internal kedua sistem.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Skripsi(Base):
    __tablename__ = "skripsi"

    # ── Kunci internal ──────────────────────────────────────────────────────
    id          = Column(Integer, primary_key=True, index=True)

    # ── Kunci dari Laravel (nullable untuk data yang tidak dari Laravel) ─────
    laravel_id  = Column(Integer, nullable=True, unique=True, index=True)

    # ── Data akademik ───────────────────────────────────────────────────────
    judul           = Column(String(500), nullable=False, index=True)
    abstrak         = Column(Text,        nullable=True)
    kata_kunci      = Column(String(500), nullable=True)
    tahun           = Column(Integer,     nullable=True)
    program_studi   = Column(String(100), nullable=True)
    nim             = Column(String(50),  nullable=True)
    nama_mahasiswa  = Column(String(200), nullable=True)

    # ── Timestamp ───────────────────────────────────────────────────────────
    created_at  = Column(DateTime, server_default=func.now())
    updated_at  = Column(DateTime, server_default=func.now(), onupdate=func.now())
