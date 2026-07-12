"""
Unit tests untuk app/utils/similarity.py

Menguji:
  - get_similarity_level()     : konversi skor ke label level
  - format_persen()            : format skor ke string persen
  - calculate_jaccard()        : Jaccard similarity antara dua teks
"""
import pytest
from app.utils.similarity import get_similarity_level, format_persen, calculate_jaccard


class TestGetSimilarityLevel:
    def test_sangat_tinggi_batas_bawah(self):
        assert get_similarity_level(0.85) == "SANGAT TINGGI"

    def test_sangat_tinggi_sempurna(self):
        assert get_similarity_level(1.0) == "SANGAT TINGGI"

    def test_sangat_tinggi_tepat_di_atas(self):
        assert get_similarity_level(0.90) == "SANGAT TINGGI"

    def test_tinggi_batas_bawah(self):
        assert get_similarity_level(0.70) == "TINGGI"

    def test_tinggi_tengah(self):
        assert get_similarity_level(0.77) == "TINGGI"

    def test_tinggi_batas_atas(self):
        assert get_similarity_level(0.849) == "TINGGI"

    def test_sedang_batas_bawah(self):
        assert get_similarity_level(0.50) == "SEDANG"

    def test_sedang_tengah(self):
        assert get_similarity_level(0.60) == "SEDANG"

    def test_sedang_batas_atas(self):
        assert get_similarity_level(0.699) == "SEDANG"

    def test_rendah_nol(self):
        assert get_similarity_level(0.0) == "RENDAH"

    def test_rendah_tengah(self):
        assert get_similarity_level(0.30) == "RENDAH"

    def test_rendah_batas_atas(self):
        assert get_similarity_level(0.499) == "RENDAH"


class TestFormatPersen:
    def test_nol(self):
        assert format_persen(0.0) == "0.0%"

    def test_satu(self):
        assert format_persen(1.0) == "100.0%"

    def test_setengah(self):
        assert format_persen(0.5) == "50.0%"

    def test_satu_desimal(self):
        assert format_persen(0.921) == "92.1%"

    def test_dibulatkan(self):
        assert format_persen(0.8734) == "87.3%"

    def test_tiga_nol(self):
        assert format_persen(0.750) == "75.0%"


class TestCalculateJaccard:
    def test_identik(self):
        assert calculate_jaccard("kucing anjing", "kucing anjing") == 1.0

    def test_tidak_ada_irisan(self):
        score = calculate_jaccard("kucing", "anjing")
        assert score == 0.0

    def test_sebagian_irisan(self):
        score = calculate_jaccard("a b", "b c")
        assert abs(score - 1 / 3) < 1e-9

    def test_satu_kosong(self):
        score = calculate_jaccard("", "kucing")
        assert score == 0.0

    def test_dua_dua_kosong(self):
        assert calculate_jaccard("", "") == 0.0

    def test_case_sensitive(self):
        score = calculate_jaccard("Sistem", "sistem")
        assert score == 0.0

    def test_duplikat_kata_dihitung_sekali(self):
        score = calculate_jaccard("a a", "a b")
        assert abs(score - 0.5) < 1e-9

    def test_judul_skripsi_mirip(self):
        a = "klasifikasi penyakit diabetes knn"
        b = "klasifikasi diabetes menggunakan knn"
        score = calculate_jaccard(a, b)
        assert abs(score - 3 / 5) < 1e-9

    def test_judul_skripsi_berbeda(self):
        a = "blockchain rekam medis keamanan"
        b = "rekomendasi musik collaborative filtering"
        score = calculate_jaccard(a, b)
        assert score == 0.0
