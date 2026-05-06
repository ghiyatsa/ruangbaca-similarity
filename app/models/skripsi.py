"""
SQLAlchemy model untuk tabel `skripsi`.

Kolom `skripsi_id` digunakan sebagai foreign-key logis ke tabel skripsi di
aplikasi Laravel utama. Untuk kompatibilitas data lama, nama kolom SQLite
dapat dimigrasikan saat startup bila masih memakai nama `laravel_id`.
"""
from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Skripsi(Base):
    __tablename__ = "skripsi"

    id = Column(Integer, primary_key=True, index=True)
    skripsi_id = Column(Integer, nullable=True, unique=True, index=True)

    judul = Column(String(500), nullable=False, index=True)
    abstrak = Column(Text, nullable=True)
    kata_kunci = Column(String(500), nullable=True)
    tahun = Column(Integer, nullable=True)
    program_studi = Column(String(100), nullable=True)
    nim = Column(String(50), nullable=True)
    nama_mahasiswa = Column(String(200), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
