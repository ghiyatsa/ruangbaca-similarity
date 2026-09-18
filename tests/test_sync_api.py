"""
Test endpoint HTTP /api/v1/sync/* dan pipeline bulk-upsert (sebelumnya 0%).

Menguji autentikasi, upsert/delete, status job, serta jalur sukses & gagal
dari pemrosesan job latar belakang tanpa menyentuh ChromaDB maupun model.
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.api.sync import _run_bulk_upsert_job
from app.repositories.sync_job_repo import SyncJobRepository


class TestAuth:
    def test_menolak_upsert_tanpa_token(self, client):
        response = client.post("/api/v1/sync/upsert", json={"judul": "judul uji lima kata"})
        assert response.status_code == 401

    def test_menolak_bulk_tanpa_token(self, client):
        response = client.post("/api/v1/sync/bulk-upsert", json={"data": []})
        assert response.status_code == 401

    def test_menolak_delete_tanpa_token(self, client):
        response = client.delete("/api/v1/sync/123")
        assert response.status_code == 401


class TestUpsertOne:
    def test_menyimpan_embedding_dan_metadata(self, client, auth_headers, fake_store, fake_embedding):
        response = client.post(
            "/api/v1/sync/upsert",
            json={
                "document_id": "skripsi_123",
                "judul": "sistem rekomendasi wisata",
                "abstrak": "abstrak singkat",
                "kata_kunci": "knn, wisata",
                "tahun": 2024,
                "nim": "2001700123",
                "nama_mahasiswa": "Alya Putri",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["document_id"] == "skripsi_123"
        assert body["skripsi_id"] == 123

        assert len(fake_store.upserts) == 1
        metadata = fake_store.upserts[0]["metadata"]
        assert metadata["document_type"] == "skripsi"
        assert metadata["tahun"] == 2024
        assert metadata["judul"] == "sistem rekomendasi wisata"

        assert fake_embedding.update_calls == 1

    def test_menolak_judul_terlalu_pendek(self, client, auth_headers):
        response = client.post(
            "/api/v1/sync/upsert",
            json={"document_id": "skripsi_1", "judul": "abc"},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestDelete:
    def test_id_angka_dipetakan_ke_prefix_skripsi(self, client, auth_headers, fake_store):
        response = client.delete("/api/v1/sync/123", headers=auth_headers)

        assert response.status_code == 204
        assert fake_store.deleted == ["skripsi_123"]

    def test_id_dengan_prefix_dipakai_apa_adanya(self, client, auth_headers, fake_store):
        response = client.delete("/api/v1/sync/internship_report_9", headers=auth_headers)

        assert response.status_code == 204
        assert fake_store.deleted == ["internship_report_9"]


class TestJobStatus:
    def test_404_saat_job_tidak_ditemukan(self, client, auth_headers):
        response = client.get("/api/v1/sync/jobs/tidak-ada", headers=auth_headers)
        assert response.status_code == 404

    def test_mengembalikan_status_job(self, client, auth_headers):
        asyncio.run(
            SyncJobRepository.create(job_id="job-1", payload_json="{}", total_received=3)
        )

        response = client.get("/api/v1/sync/jobs/job-1", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["job_id"] == "job-1"
        assert body["status"] == "pending"
        assert body["total_received"] == 3


class TestBulkUpsert:
    def test_menolak_data_kosong(self, client, auth_headers):
        response = client.post(
            "/api/v1/sync/bulk-upsert",
            json={"data": []},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_menerima_data_dan_membuat_job(self, client, auth_headers, fake_store):
        # Job latar belakang benar-benar dieksekusi oleh TestClient, jadi
        # jumlah vector dibuat konsisten agar jalur sukses yang diuji.
        fake_store._count = 2

        response = client.post(
            "/api/v1/sync/bulk-upsert",
            json={
                "data": [
                    {"document_id": "skripsi_1", "judul": "judul uji lima kata"},
                    {"document_id": "skripsi_2", "judul": "judul lain lima kata"},
                ],
                "reset_index": True,
            },
            headers=auth_headers,
        )

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "accepted"
        assert body["total_received"] == 2

        job = asyncio.run(SyncJobRepository.find_by_id(body["job_id"]))
        assert job is not None
        assert job.total_received == 2


class TestBulkJobPipeline:
    """Uji langsung pipeline job (tanpa mengandalkan penjadwalan background)."""

    def _app_state(self, fake_embedding, fake_store):
        return SimpleNamespace(embedding_service=fake_embedding, vector_store=fake_store)

    def _payload(self, ids, reset=False):

        from app.api.sync import _serialize_payload
        from app.schemas.document import SyncItem

        items = [
            SyncItem(document_id=f"skripsi_{i}", judul=f"judul dokumen nomor {i}")
            for i in ids
        ]
        return _serialize_payload(items, reset)

    def test_menandai_selesai_dan_menyimpan_batch(self, fake_embedding, fake_store):
        fake_store._count = 2
        job = asyncio.run(
            SyncJobRepository.create(
                job_id="job-ok",
                payload_json=self._payload([1, 2]),
                total_received=2,
            )
        )

        asyncio.run(_run_bulk_upsert_job(self._app_state(fake_embedding, fake_store), job.id))

        stored = asyncio.run(SyncJobRepository.find_by_id("job-ok"))
        assert stored.status == "completed"
        assert stored.total_processed == 2
        assert len(fake_store.upserts) == 1
        assert fake_store.upserts[0]["ids"] == ["skripsi_1", "skripsi_2"]

    def test_gagal_saat_jumlah_vector_tidak_konsisten(self, fake_embedding, fake_store):
        # reset_index=True menuntut jumlah vector akhir == jumlah dokumen unik.
        fake_store._count = 1  # sengaja tidak cocok dengan 2 dokumen
        job = asyncio.run(
            SyncJobRepository.create(
                job_id="job-bad",
                payload_json=self._payload([1, 2], reset=True),
                total_received=2,
            )
        )

        asyncio.run(_run_bulk_upsert_job(self._app_state(fake_embedding, fake_store), job.id))

        stored = asyncio.run(SyncJobRepository.find_by_id("job-bad"))
        assert stored.status == "failed"
        assert "tidak konsisten" in stored.error_message

    def test_menjalankan_reset_index_saat_diminta(self, fake_embedding, fake_store):
        fake_store._count = 1
        job = asyncio.run(
            SyncJobRepository.create(
                job_id="job-reset",
                payload_json=self._payload([5], reset=True),
                total_received=1,
            )
        )

        asyncio.run(_run_bulk_upsert_job(self._app_state(fake_embedding, fake_store), job.id))

        assert fake_store.reset_called is True

    def test_job_tidak_ditemukan_tidak_menyebabkan_error(self, fake_embedding, fake_store):
        # Tidak melempar exception walau job tidak ada.
        asyncio.run(
            _run_bulk_upsert_job(self._app_state(fake_embedding, fake_store), "tidak-ada")
        )
        assert fake_store.upserts == []


class TestVerifyIndexedTotal:
    """Helper validasi jumlah vector (diekstrak dari _run_bulk_upsert_job)."""

    def test_reset_menuntut_jumlah_sama_persis(self):
        from app.api.sync import _verify_indexed_total

        _verify_indexed_total(True, 5, 5)  # tidak melempar

        with pytest.raises(RuntimeError, match="tidak konsisten"):
            _verify_indexed_total(True, 5, 4)

    def test_upsert_bertahap_hanya_menolak_jika_kurang(self):
        from app.api.sync import _verify_indexed_total

        _verify_indexed_total(False, 5, 5)  # sama -> ok
        _verify_indexed_total(False, 5, 9)  # lebih besar -> ok (dokumen lama)

        with pytest.raises(RuntimeError, match="lebih kecil"):
            _verify_indexed_total(False, 5, 4)
