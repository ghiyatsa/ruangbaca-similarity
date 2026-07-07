"""
Unit tests untuk Pydantic schemas (app/schemas/document.py).

Menguji:
  - SyncItem           : validasi payload sinkronisasi dari Laravel
  - SimilarityCheckRequest : validasi payload cek kemiripan
"""
import pytest
from pydantic import ValidationError
from app.schemas.document import SyncItem, SimilarityCheckRequest


class TestSyncItem:
    def test_payload_lengkap(self):
        item = SyncItem(
            document_id="skripsi_123",
            document_type="skripsi",
            judul="Sistem Deteksi Kemiripan Judul Skripsi",
            abstrak="Penelitian ini membahas sistem deteksi.",
            kata_kunci="nlp, similarity",
            tahun=2024,
            program_studi="Informatika",
            nim="210170001",
            nama_mahasiswa="Budi Santoso",
        )
        assert item.document_id == "skripsi_123"
        assert item.document_type == "skripsi"
        assert item.judul == "Sistem Deteksi Kemiripan Judul Skripsi"

    def test_payload_minimal(self):
        item = SyncItem(document_id="skripsi_1", judul="Judul Skripsi Minimal")
        assert item.document_id == "skripsi_1"
        assert item.abstrak is None
        assert item.kata_kunci is None

    def test_alias_skripsi_id(self):
        """Kompatibilitas backward: skripsi_id diterima sebagai document_id."""
        item = SyncItem(skripsi_id=99, judul="Judul Menggunakan Alias skripsi_id")
        assert item.document_id == "skripsi_99"
        assert item.skripsi_id == 99

    def test_document_type_default_skripsi(self):
        item = SyncItem(document_id="doc_1", judul="Judul Tanpa Tipe Dokumen")
        assert item.document_type == "skripsi"

    def test_document_type_internship_report(self):
        item = SyncItem(
            document_id="internship_report_5",
            document_type="internship_report",
            judul="Laporan Kerja Praktik di PT. ABC",
        )
        assert item.document_type == "internship_report"

    def test_judul_terlalu_pendek(self):
        with pytest.raises(ValidationError):
            SyncItem(document_id="skripsi_1", judul="KP")

    def test_judul_terlalu_panjang(self):
        with pytest.raises(ValidationError):
            SyncItem(document_id="skripsi_1", judul="A" * 501)

    def test_tahun_di_bawah_batas(self):
        with pytest.raises(ValidationError):
            SyncItem(document_id="skripsi_1", judul="Judul Valid Cukup Panjang", tahun=1989)

    def test_tahun_di_atas_batas(self):
        with pytest.raises(ValidationError):
            SyncItem(document_id="skripsi_1", judul="Judul Valid Cukup Panjang", tahun=2101)

    def test_bobot_negatif_ditolak(self):
        with pytest.raises(ValidationError):
            SyncItem(
                document_id="skripsi_1",
                judul="Judul Valid Cukup Panjang",
                bobot_judul=-0.5,
            )

    def test_document_id_otomatis_dari_skripsi_id_dan_type(self):
        item = SyncItem(
            skripsi_id=42,
            document_type="internship_report",
            judul="Laporan Kerja Praktik Valid Panjang",
        )
        assert item.document_id == "internship_report_42"

    def test_tanpa_document_id_dan_skripsi_id_error(self):
        with pytest.raises(ValidationError):
            SyncItem(judul="Judul Valid Cukup Panjang")


class TestSimilarityCheckRequest:
    def test_default_values(self):
        req = SimilarityCheckRequest(judul="Sistem Rekomendasi Berbasis Web")
        assert req.top_k == 5
        assert req.threshold == 0.5
        assert req.document_type is None

    def test_custom_values(self):
        req = SimilarityCheckRequest(
            judul="Deteksi Penyakit Tanaman Padi CNN",
            top_k=10,
            threshold=0.75,
            document_type="skripsi",
        )
        assert req.top_k == 10
        assert req.threshold == 0.75
        assert req.document_type == "skripsi"

    def test_judul_terlalu_pendek(self):
        with pytest.raises(ValidationError):
            SimilarityCheckRequest(judul="KP")

    def test_top_k_minimum(self):
        req = SimilarityCheckRequest(judul="Judul Valid Cukup Panjang", top_k=1)
        assert req.top_k == 1

    def test_top_k_maksimum(self):
        req = SimilarityCheckRequest(judul="Judul Valid Cukup Panjang", top_k=20)
        assert req.top_k == 20

    def test_top_k_di_luar_batas(self):
        with pytest.raises(ValidationError):
            SimilarityCheckRequest(judul="Judul Valid Cukup Panjang", top_k=21)

    def test_threshold_valid_range(self):
        req = SimilarityCheckRequest(judul="Judul Valid Cukup Panjang", threshold=0.0)
        assert req.threshold == 0.0
        req2 = SimilarityCheckRequest(judul="Judul Valid Cukup Panjang", threshold=1.0)
        assert req2.threshold == 1.0

    def test_threshold_di_luar_batas(self):
        with pytest.raises(ValidationError):
            SimilarityCheckRequest(judul="Judul Valid Cukup Panjang", threshold=1.1)
