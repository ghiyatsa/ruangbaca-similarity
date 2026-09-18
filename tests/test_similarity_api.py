"""
Test endpoint HTTP /api/v1/similarity/* (sebelumnya 0% coverage).

Menguji jalur kritis: autentikasi, validasi, pemetaan hasil pencarian,
filter document_type, agregasi statistik, dan peringatan kemiripan tinggi.
"""


class TestAuth:
    def test_menolak_tanpa_token(self, client):
        response = client.post("/api/v1/similarity/check", json={"judul": "judul uji lima kata"})
        assert response.status_code == 401

    def test_menolak_token_salah(self, client):
        response = client.post(
            "/api/v1/similarity/check",
            json={"judul": "judul uji lima kata"},
            headers={"X-Similarity-Api-Secret": "token-palsu"},
        )
        assert response.status_code == 401

    def test_menerima_bearer_token(self, client):
        from app.core.config import settings

        response = client.get(
            "/api/v1/similarity/stats",
            headers={"Authorization": f"Bearer {settings.SYNC_SECRET}"},
        )
        assert response.status_code == 200


class TestCheckSimilarity:
    def test_404_saat_index_kosong(self, client, auth_headers):
        response = client.post(
            "/api/v1/similarity/check",
            json={"judul": "judul uji lima kata"},
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert "Belum ada data" in response.json()["detail"]

    def test_422_judul_terlalu_pendek(self, client, auth_headers):
        response = client.post(
            "/api/v1/similarity/check",
            json={"judul": "abc"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_memfilter_hasil_di_bawah_threshold(self, client, auth_headers, fake_store):
        fake_store._count = 3
        # hybrid = 0.7*semantic + 0.3*jaccard; semantic 0.10 -> jauh di bawah threshold
        fake_store._search_results = [
            {
                "id": "skripsi_1",
                "similarity_score": 0.10,
                "document": "judul uji lima kata",
                "document_id": "skripsi_1",
                "document_type": "skripsi",
            }
        ]

        response = client.post(
            "/api/v1/similarity/check",
            json={"judul": "judul uji lima kata", "threshold": 0.9},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["total_found"] == 0

    def test_memeta_hasil_skripsi_dan_menghasilkan_level(self, client, auth_headers, fake_store):
        fake_store._count = 2
        fake_store._search_results = [
            {
                "id": "skripsi_42",
                "similarity_score": 0.95,
                "document": "sistem rekomendasi wisata",
                "document_id": "skripsi_42",
                "document_type": "skripsi",
            }
        ]

        response = client.post(
            "/api/v1/similarity/check",
            json={"judul": "sistem rekomendasi wisata", "threshold": 0.5},
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total_found"] == 1

        result = body["results"][0]
        assert result["document_id"] == 42
        assert result["document_type"] == "skripsi"
        assert result["skripsi_id"] == 42
        assert result["similarity_persen"].endswith("%")
        assert result["level"] in {"SANGAT TINGGI", "TINGGI", "SEDANG", "RENDAH"}

    def test_menandai_laporan_kp_tanpa_skripsi_id(self, client, auth_headers, fake_store):
        fake_store._count = 1
        fake_store._search_results = [
            {
                "id": "internship_report_7",
                "similarity_score": 0.9,
                "document": "laporan kerja praktek",
                "document_id": "internship_report_7",
                "document_type": "internship_report",
            }
        ]

        response = client.post(
            "/api/v1/similarity/check",
            json={"judul": "laporan kerja praktek lapangan", "threshold": 0.5},
            headers=auth_headers,
        )

        result = response.json()["results"][0]
        assert result["document_type"] == "internship_report"
        assert result["skripsi_id"] is None

    def test_memberi_peringatan_saat_kemiripan_sangat_tinggi(self, client, auth_headers, fake_store):
        fake_store._count = 1
        fake_store._search_results = [
            {
                "id": "skripsi_9",
                "similarity_score": 0.99,
                "document": "analisis sentimen ulasan",
                "document_id": "skripsi_9",
                "document_type": "skripsi",
            }
        ]

        response = client.post(
            "/api/v1/similarity/check",
            json={"judul": "analisis sentimen ulasan", "threshold": 0.5},
            headers=auth_headers,
        )

        body = response.json()
        assert body["peringatan"] is not None
        assert "SANGAT TINGGI" in body["peringatan"]

    def test_menyortir_hasil_menurun(self, client, auth_headers, fake_store):
        fake_store._count = 2
        fake_store._search_results = [
            {
                "id": "skripsi_1",
                "similarity_score": 0.72,
                "document": "analisis sentimen ulasan",
                "document_id": "skripsi_1",
                "document_type": "skripsi",
            },
            {
                "id": "skripsi_2",
                "similarity_score": 0.98,
                "document": "analisis sentimen ulasan",
                "document_id": "skripsi_2",
                "document_type": "skripsi",
            },
        ]

        response = client.post(
            "/api/v1/similarity/check",
            json={"judul": "analisis sentimen ulasan", "threshold": 0.5},
            headers=auth_headers,
        )

        scores = [r["similarity_score"] for r in response.json()["results"]]
        assert scores == sorted(scores, reverse=True)


class TestCompare:
    def test_mengembalikan_skor_dan_detail(self, client, auth_headers):
        response = client.post(
            "/api/v1/similarity/compare",
            params={"judul_a": "analisis sentimen ulasan", "judul_b": "analisis sentimen opini"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert 0.0 <= body["similarity_score"] <= 1.0
        assert set(body["detail"]) == {"semantic_score", "lexical_score"}
        assert body["level"]


class TestStats:
    def test_index_kosong_mengembalikan_nol(self, client, auth_headers):
        response = client.get("/api/v1/similarity/stats", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {
            "total_indexed": 0,
            "distribusi_program_studi": {},
            "distribusi_tahun": {},
        }

    def test_mengagregasi_prodi_dan_tahun(self, client, auth_headers, fake_store):
        fake_store._count = 3
        fake_store.collection._metadatas = [
            {"program_studi": "Informatika", "tahun": 2024},
            {"program_studi": "Informatika", "tahun": 2024},
            {"program_studi": "Sistem Informasi", "tahun": 2023},
        ]

        response = client.get("/api/v1/similarity/stats", headers=auth_headers)

        body = response.json()
        assert body["total_indexed"] == 3
        assert body["distribusi_program_studi"] == {"Informatika": 2, "Sistem Informasi": 1}
        assert body["distribusi_tahun"] == {"2024": 2, "2023": 1}
