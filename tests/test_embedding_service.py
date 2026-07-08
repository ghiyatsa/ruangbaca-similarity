"""
Unit tests untuk EmbeddingService (metode non-async / pure logic).

Menguji:
  - clean_title()       : pembersihan stopwords dan normalisasi teks
  - _resolve_weights()  : normalisasi bobot judul/abstrak/kata_kunci
  - build_index_text()  : penggabungan bagian teks untuk indeks
  - build_query_text()  : normalisasi teks query
"""
import pytest
from app.services.embedding_service import EmbeddingService


@pytest.fixture
def svc():
    """Instance EmbeddingService tanpa memuat model (hanya metode pure-logic)."""
    return EmbeddingService()


class TestCleanTitle:
    def test_hapus_stopword_indonesia(self, svc):
        result = svc.clean_title("Sistem Informasi Manajemen")
        # "dan", "yang", dll dihapus — "sistem" juga termasuk stopword
        assert "sistem" not in result.lower()

    def test_hapus_boilerplate_akademik(self, svc):
        result = svc.clean_title("Implementasi Sistem Berbasis Web")
        words = result.split()
        # "implementasi", "sistem", "berbasis" adalah stopwords
        assert all(w.lower() not in {"implementasi", "sistem", "berbasis"} for w in words)

    def test_pertahankan_kata_substantif(self, svc):
        result = svc.clean_title("Deteksi Penyakit Diabetes Menggunakan KNN")
        # "penyakit", "diabetes", "knn" harus tetap ada
        result_lower = result.lower()
        assert "penyakit" in result_lower
        assert "diabetes" in result_lower
        assert "knn" in result_lower

    def test_hapus_karakter_non_alfanumerik(self, svc):
        result = svc.clean_title("Judul: Dengan, Tanda! Baca?")
        assert ":" not in result
        assert "," not in result
        assert "!" not in result
        assert "?" not in result

    def test_lowercase(self, svc):
        result = svc.clean_title("BLOCKCHAIN KEAMANAN DATA")
        assert result == result.lower()

    def test_hapus_kata_pendek(self, svc):
        # Kata dengan panjang < 3 karakter harus dibuang
        result = svc.clean_title("ai di era digital")
        words = result.split()
        assert all(len(w) >= 3 for w in words)

    def test_judul_kosong(self, svc):
        result = svc.clean_title("")
        assert result == ""

    def test_fallback_jika_semua_stopwords(self, svc):
        # Jika semua kata adalah stopword, kembalikan judul asli (tidak kosong)
        result = svc.clean_title("sistem dan aplikasi")
        assert len(result) > 0

    def test_judul_inggris(self, svc):
        result = svc.clean_title("Deep Learning for Image Classification")
        result_lower = result.lower()
        # "for", "the" adalah stopwords inggris
        assert "for" not in result_lower.split()
        # "deep", "learning", "image", "classification" harus tetap ada
        assert "deep" in result_lower
        assert "learning" in result_lower

    def test_dynamic_stopwords_digunakan(self, svc):
        svc.dynamic_stopwords = {"blockchain"}
        result = svc.clean_title("Blockchain Keamanan Data")
        assert "blockchain" not in result.lower()

    def test_preserve_technical_hyphenated_terms(self, svc):
        # Istilah seperti k-means, ui/ux, c4.5 harus dipertahankan sebagai satu kata tanpa karakter khusus
        assert "kmeans" in svc.clean_title("Analisis K-Means")
        assert "ecommerce" in svc.clean_title("Sistem E-Commerce")
        assert "uiux" in svc.clean_title("Evaluasi UI/UX")
        assert "c45" in svc.clean_title("Klasifikasi C4.5")


class TestResolveWeights:
    def test_bobot_default_jika_none(self, svc):
        w_j, w_a, w_kk = svc._resolve_weights(None, None, None)
        total = w_j + w_a + w_kk
        assert abs(total - 1.0) < 1e-6

    def test_bobot_custom_dinormalisasi(self, svc):
        w_j, w_a, w_kk = svc._resolve_weights(2.0, 1.0, 1.0)
        assert abs(w_j - 0.5) < 1e-6
        assert abs(w_a - 0.25) < 1e-6
        assert abs(w_kk - 0.25) < 1e-6

    def test_total_selalu_satu(self, svc):
        w_j, w_a, w_kk = svc._resolve_weights(0.7, 0.2, 0.1)
        assert abs(w_j + w_a + w_kk - 1.0) < 1e-6

    def test_bobot_negatif_diclamp_ke_nol(self, svc):
        w_j, w_a, w_kk = svc._resolve_weights(-1.0, 1.0, 0.0)
        # -1.0 di-clamp ke 0.0, sehingga hanya bobot abstrak yang aktif
        assert w_j == 0.0
        assert abs(w_a - 1.0) < 1e-6

    def test_semua_nol_fallback_ke_default(self, svc):
        # Jika semua custom bobot 0, gunakan default settings
        w_j, w_a, w_kk = svc._resolve_weights(0.0, 0.0, 0.0)
        total = w_j + w_a + w_kk
        assert abs(total - 1.0) < 1e-6
        # Bobot judul default (0.7) harus mendominasi
        assert w_j > w_a
        assert w_j > w_kk

    def test_satu_bobot_saja(self, svc):
        w_j, w_a, w_kk = svc._resolve_weights(1.0, 0.0, 0.0)
        assert abs(w_j - 1.0) < 1e-6
        assert w_a == 0.0
        assert w_kk == 0.0


class TestBuildIndexText:
    def test_hanya_judul(self):
        result = EmbeddingService.build_index_text("Judul Skripsi")
        assert result == "Judul Skripsi"

    def test_judul_dan_abstrak(self):
        result = EmbeddingService.build_index_text("Judul", abstrak="Ini abstrak")
        assert "Judul" in result
        assert "Ini abstrak" in result
        assert " | " in result

    def test_judul_abstrak_kata_kunci(self):
        result = EmbeddingService.build_index_text(
            "Judul", abstrak="Abstrak", kata_kunci="nlp, knn"
        )
        parts = result.split(" | ")
        assert len(parts) == 3
        assert parts[0] == "Judul"
        assert parts[1] == "Abstrak"
        assert parts[2] == "nlp, knn"

    def test_abstrak_dipotong_sesuai_max_chars(self):
        abstrak_panjang = "x" * 1000
        result = EmbeddingService.build_index_text("Judul", abstrak=abstrak_panjang)
        # Bagian abstrak tidak boleh lebih dari ABSTRAK_MAX_CHARS
        from app.core.config import settings
        abstrak_part = result.split(" | ")[1]
        assert len(abstrak_part) <= settings.ABSTRAK_MAX_CHARS


class TestBuildQueryText:
    def test_strip_whitespace(self):
        result = EmbeddingService.build_query_text("  Judul Skripsi  ")
        assert result == "Judul Skripsi"

    def test_tidak_mengubah_isi(self):
        result = EmbeddingService.build_query_text("Deteksi Wajah")
        assert result == "Deteksi Wajah"
