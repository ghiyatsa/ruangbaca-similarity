---
title: Skripsi Similarity API
sdk: docker
app_port: 7860
---

# Skripsi Similarity API

API deteksi kemiripan judul skripsi berbasis FastAPI, Sentence Transformers, dan ChromaDB.

Repo ini sekarang memakai arsitektur `vector_only`:

- Laravel/ruangbaca tetap menjadi source of truth data skripsi
- FastAPI hanya menerima payload sinkronisasi, membuat embedding, dan menyimpan vector
- SQLite lokal hanya dipakai untuk menyimpan status `sync_jobs`
- Hasil similarity mengembalikan `id` sumber + skor, lalu detail data diambil lagi oleh Laravel

## Ringkasan Arsitektur

- FastAPI melayani endpoint similarity dan sync
- MySQL di Laravel menyimpan data skripsi utama
- ChromaDB menyimpan embedding untuk semantic similarity
- Model embedding lokal dibundel ke image dan dipakai dalam mode offline
- Runtime memprioritaskan ONNX quantized agar inferensi CPU lebih ringan

## Endpoint Utama

### Meta

- `GET /`
- `GET /health`

### Similarity

- `POST /api/v1/similarity/check`
- `POST /api/v1/similarity/compare`

### Sync dari Laravel

Semua endpoint sync wajib header:

```text
Authorization: Bearer <SYNC_SECRET>
```

- `POST /api/v1/sync/upsert`
- `POST /api/v1/sync/bulk-upsert`
- `GET /api/v1/sync/jobs/{job_id}`
- `DELETE /api/v1/sync/{skripsi_id}`

## Contoh Payload Sync

Payload baru yang direkomendasikan:

```json
{
  "skripsi_id": 123,
  "judul": "Sistem Deteksi Kemiripan Judul Skripsi",
  "abstrak": "Abstrak opsional",
  "kata_kunci": "nlp, similarity",
  "tahun": 2026,
  "program_studi": "Informatika",
  "nim": "210170001",
  "nama_mahasiswa": "Nama Mahasiswa"
}
```

Payload lama berikut masih diterima sementara:

```json
{
  "laravel_id": 123,
  "judul": "Sistem Deteksi Kemiripan Judul Skripsi"
}
```

## Bentuk Hasil Similarity

Contoh `POST /api/v1/similarity/check`:

```json
{
  "query": {
    "judul": "Sistem Deteksi Kemiripan Judul Skripsi"
  },
  "total_found": 2,
  "results": [
    {
      "id": 123,
      "similarity_score": 0.9211,
      "similarity_persen": "92.11%",
      "level": "SANGAT TINGGI"
    },
    {
      "id": 88,
      "similarity_score": 0.8734,
      "similarity_persen": "87.34%",
      "level": "TINGGI"
    }
  ]
}
```

Laravel lalu mengambil detail skripsi berdasarkan daftar `id` tersebut dari MySQL.

## Menjalankan Lokal

### Python langsung

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python main.py
```

API lokal akan berjalan di:

- `http://localhost:8181`
- docs: `http://localhost:8181/docs`

### Docker Compose

```bash
docker compose build
docker compose up -d
docker compose logs -f similarity-api
```

Port host lokal:

- `http://localhost:8181`

Port internal container:

- `7860`

## Integrasi Laravel

Set environment di Laravel:

```env
SIMILARITY_API_URL=https://<username>-<space-name>.hf.space
SIMILARITY_API_SECRET=<nilai SYNC_SECRET yang sama>
```

Contoh observer Laravel:

```php
class SkripsiObserver
{
    public function saved(Skripsi $skripsi): void
    {
        Http::withToken(config('services.similarity.secret'))
            ->post(config('services.similarity.url') . '/api/v1/sync/upsert', [
                'skripsi_id'     => $skripsi->id,
                'judul'          => $skripsi->judul,
                'abstrak'        => $skripsi->abstrak,
                'kata_kunci'     => $skripsi->kata_kunci,
                'tahun'          => $skripsi->tahun,
                'program_studi'  => $skripsi->program_studi,
                'nim'            => $skripsi->nim,
                'nama_mahasiswa' => $skripsi->nama_mahasiswa,
            ]);
    }

    public function deleted(Skripsi $skripsi): void
    {
        Http::withToken(config('services.similarity.secret'))
            ->delete(config('services.similarity.url') . '/api/v1/sync/' . $skripsi->id);
    }
}
```

Rekomendasi integrasi:

- gunakan `bulk-upsert` untuk initial sync
- gunakan observer untuk create, update, delete setelah initial sync
- setelah `check` mengembalikan daftar `id`, detail dan business rule tetap diambil di Laravel

## Reindex

Karena service ini tidak lagi menyimpan salinan data skripsi lokal, reindex dilakukan dengan mengirim ulang export JSON dari aplikasi utama:

```bash
python scripts/reindex.py --token <SYNC_SECRET> --input data-skripsi.json --batch-size 100
```

Jika API berjalan di Docker:

```bash
docker compose exec similarity-api python scripts/reindex.py --url http://localhost:7860 --token <SYNC_SECRET> --input /data/data-skripsi.json --batch-size 100
```

Gunakan reindex saat:

- model embedding berubah
- metadata vector store lama perlu dirapikan
- migrasi server atau storage
- ChromaDB kosong atau rusak

## Keamanan

- `SYNC_SECRET` wajib minimal 16 karakter dan sebaiknya acak panjang
- verifikasi token sync memakai constant-time compare
- container berjalan sebagai user non-root UID `1000`
- model tidak di-download saat runtime

## Catatan Migrasi

- tabel SQLite lama yang sebelumnya menyimpan cache data skripsi tidak lagi dipakai oleh aplikasi
- metadata vector store lama yang masih menyimpan field tambahan tetap bisa terbaca
- untuk merapikan metadata vector store agar minimum, jalankan reindex sekali setelah deploy versi ini
