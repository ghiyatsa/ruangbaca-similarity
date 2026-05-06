---
title: Skripsi Similarity API
sdk: docker
app_port: 7860
---

# Skripsi Similarity API

API deteksi kemiripan judul skripsi berbasis FastAPI, Sentence Transformers, dan ChromaDB. Repo ini sudah disiapkan untuk:

- deployment Docker lokal
- deployment ke Hugging Face Spaces
- integrasi sinkronisasi data dari Laravel

## Ringkasan Arsitektur

- FastAPI melayani endpoint similarity, skripsi, dan sync.
- SQLite menyimpan metadata skripsi.
- ChromaDB menyimpan embedding untuk pencarian kemiripan.
- Model embedding lokal dibundel ke image dan dipakai dalam mode offline.
- Runtime memprioritaskan ONNX quantized agar inferensi CPU lebih ringan.

## Perubahan Penting

- Nama field publik untuk ID sumber sekarang adalah `skripsi_id`.
- Payload lama yang masih mengirim `laravel_id` masih diterima sementara pada endpoint sync agar rollout Laravel tidak langsung putus.
- Metadata hasil similarity sekarang mengembalikan `skripsi_id`.
- Port internal container untuk Hugging Face Spaces adalah `7860`.
- Port lokal lewat `docker compose` tetap diakses dari host pada `8181`.

## Endpoint Utama

### Meta

- `GET /`
- `GET /health`

### Similarity

- `POST /api/v1/similarity/check`
- `POST /api/v1/similarity/compare`

### Skripsi

- `GET /api/v1/skripsi`
- `GET /api/v1/skripsi/{id}`
- `DELETE /api/v1/skripsi/{id}`

### Sync dari Laravel

Semua endpoint sync wajib header:

```text
Authorization: Bearer <SYNC_SECRET>
```

- `POST /api/v1/sync/upsert`
- `POST /api/v1/sync/bulk-upsert`
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

## Deploy ke Hugging Face Spaces

Repo ini sudah disiapkan untuk Docker Space.

### 1. Buat Space

- pilih SDK `Docker`
- push repo ini ke Space
- `README.md` sudah memiliki front matter `sdk: docker` dan `app_port: 7860`

### 2. Atur Secrets dan Variables di Space Settings

Minimal set:

- `SYNC_SECRET`

Opsional tapi dianjurkan:

- `ALLOWED_ORIGINS`
- `LOG_LEVEL`
- `INFERENCE_CONCURRENCY`
- `BULK_SYNC_CHUNK_SIZE`

Contoh runtime variables untuk Space:

```text
ALLOWED_ORIGINS=https://your-laravel-domain.example
LOG_LEVEL=INFO
INFERENCE_CONCURRENCY=2
BULK_SYNC_CHUNK_SIZE=50
```

### 3. Storage dan Persistensi

- SQLite, ChromaDB, dan cache Hugging Face diarahkan ke `/data`
- pada Hugging Face Spaces, data di disk akan hilang saat restart jika Anda belum menambahkan persistent storage
- jika ingin hasil sync tetap aman antar restart, aktifkan persistent storage untuk Space

### 4. Catatan Operasional

- endpoint sync bersifat public di internet, jadi `SYNC_SECRET` wajib kuat dan tidak boleh dibocorkan
- batasi siapa yang mengetahui URL sync dan secret
- setelah deploy pertama, lakukan sync dari Laravel lalu cek `/health`
- bila metadata lama masih muncul sebagai `laravel_id` di vector store lama, jalankan reindex sekali

## Integrasi Laravel

Set environment di Laravel:

```env
SIMILARITY_API_URL=https://<username>-<space-name>.hf.space
SIMILARITY_API_SECRET=<nilai SYNC_SECRET yang sama>
```

Contoh observer Laravel yang sudah memakai `skripsi_id`:

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

### Rekomendasi Integrasi Laravel

- gunakan `bulk-upsert` untuk initial sync
- gunakan observer untuk create, update, delete setelah initial sync
- jika Anda sedang rollout bertahap, payload lama `laravel_id` masih akan diterima, tetapi sebaiknya segera ganti ke `skripsi_id`

## Reindex

Setelah data selesai disinkron dari Laravel, reindex bisa dijalankan untuk membangun ulang embedding di ChromaDB:

```bash
python scripts/reindex.py --token <SYNC_SECRET> --batch-size 100
```

Jika API berjalan di Docker:

```bash
docker compose exec similarity-api python scripts/reindex.py --url http://localhost:7860 --token <SYNC_SECRET> --batch-size 100
```

Gunakan reindex saat:

- model embedding berubah
- metadata ChromaDB lama perlu diperbarui
- Anda migrasi server atau storage
- ChromaDB kosong atau rusak

## Keamanan

- `SYNC_SECRET` wajib minimal 16 karakter dan sebaiknya acak panjang
- verifikasi token sync memakai constant-time compare
- container berjalan sebagai user non-root UID `1000`, cocok untuk Hugging Face Spaces
- model tidak di-download saat runtime
- thread CPU default diturunkan agar container lebih hemat resource

## Verifikasi Setelah Deploy

### Health check

```bash
curl https://<username>-<space-name>.hf.space/health
```

### Cek similarity

```bash
curl -X POST https://<username>-<space-name>.hf.space/api/v1/similarity/check \
  -H "Content-Type: application/json" \
  -d "{\"judul\":\"Sistem Deteksi Kemiripan Judul Skripsi\"}"
```

## Catatan Migrasi Data Lama

- database SQLite lama yang masih memakai kolom `laravel_id` akan dimigrasikan otomatis saat startup menjadi `skripsi_id`
- hasil similarity lama yang metadata ChromaDB-nya masih memakai `laravel_id` tetap dibaca kompatibel
- untuk merapikan metadata vector store sepenuhnya, jalankan reindex sekali setelah deploy versi baru
