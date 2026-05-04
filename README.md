# Skripsi Similarity API v2

API deteksi kemiripan judul skripsi berbasis **Sentence Transformers** dan **ChromaDB**.  
Dibangun dengan FastAPI, dirancang untuk diintegrasikan dengan aplikasi Laravel sebagai backend ML terpisah.

---

## Arsitektur

```
┌──────────────────────────────────────────────────────────┐
│                    FastAPI Application                    │
│                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────────┐  │
│  │  /similarity │  │  /skripsi   │  │  /sync (auth)  │  │
│  │  rate-limited│  │  CRUD       │  │  Laravel sync  │  │
│  └──────┬──────┘  └──────┬──────┘  └───────┬────────┘  │
│         │                │                  │            │
│  ┌──────▼──────────────────────────────────▼────────┐   │
│  │              Service Layer                        │   │
│  │  EmbeddingService (SentenceTransformers / ONNX)  │   │
│  │  VectorStore (ChromaDB — async via executor)     │   │
│  └──────────────────┬──────────────────────────────┘   │
│                     │                                    │
│  ┌──────────────────▼──────────────────────────────┐   │
│  │              Repository Layer                    │   │
│  │  SkripsiRepository → SQLite (aiosqlite)          │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

**Database:**
- **SQLite** (via SQLAlchemy 2.0 async) — menyimpan metadata skripsi (judul, abstrak, NIM, dll)
- **ChromaDB** — menyimpan vector embedding untuk pencarian kemiripan semantik

---

## Stack Teknologi

| Komponen | Library | Versi |
|---|---|---|
| Web Framework | FastAPI + Uvicorn | 0.136 / 0.46 |
| ML/NLP | Sentence-Transformers | 5.4 |
| ONNX Runtime | Optimum[onnxruntime] | 1.24 |
| Vector Store | ChromaDB | 1.5 |
| Relational DB | SQLAlchemy 2.0 + aiosqlite | 2.0.49 |
| Validasi | Pydantic v2 + pydantic-settings | 2.13 / 2.7 |
| Rate Limiting | SlowAPI | 0.1.9 |
| Caching | cachetools (LRUCache) | 5.5 |
| Model default | paraphrase-multilingual-MiniLM-L12-v2 | — |

---

## Struktur Proyek

```
thesis-similarity/
├── app/
│   ├── api/
│   │   ├── deps.py           # Shared dependencies (auth token)
│   │   ├── similarity.py     # Endpoint cek kemiripan (rate-limited)
│   │   ├── skripsi.py        # CRUD skripsi
│   │   └── sync.py           # Sinkronisasi dari Laravel
│   ├── core/
│   │   ├── config.py         # pydantic-settings (validasi & .env)
│   │   ├── database.py       # SQLAlchemy async engine + session
│   │   ├── limiter.py        # SlowAPI + inference semaphore
│   │   └── logging_config.py # Structured logging
│   ├── models/
│   │   └── skripsi.py        # SQLAlchemy ORM model
│   ├── repositories/
│   │   └── skripsi_repo.py   # Data access layer (Repository pattern)
│   ├── schemas/
│   │   └── skripsi.py        # Pydantic request/response schemas
│   ├── services/
│   │   ├── embedding_service.py  # ML inference + LRU cache + semaphore
│   │   └── vector_store.py       # ChromaDB (non-blocking via executor)
│   └── utils/
│       ├── metadata.py
│       └── similarity.py
├── .env                      # Konfigurasi lokal (tidak di-commit)
├── .env.example              # Template konfigurasi
├── Dockerfile                # Multi-stage build
├── docker-compose.yml        # Deployment production
├── main.py                   # Entry point FastAPI
└── requirements.txt
```

---

## Instalasi & Menjalankan (Lokal)

### Prasyarat
- Python 3.11+
- pip

### Setup

```bash
# 1. Clone dan masuk ke direktori
cd thesis-similarity

# 2. Buat virtual environment (opsional tapi disarankan)
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Salin dan sesuaikan konfigurasi
cp .env.example .env
# Edit .env — minimal isi SYNC_SECRET dengan token acak (min 16 karakter)
# Generate: python -c "import secrets; print(secrets.token_hex(32))"

# 5. Jalankan server
python main.py
# atau
uvicorn main:app --host 0.0.0.0 --port 8181 --reload
```

Server berjalan di: **http://localhost:8181**  
Dokumentasi API: **http://localhost:8181/docs**

---

## Konfigurasi (.env)

| Variable | Default | Keterangan |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./skripsi.db` | Path SQLite database |
| `CHROMA_DB_PATH` | `./chroma_db` | Direktori ChromaDB |
| `COLLECTION_NAME` | `skripsi_embeddings` | Nama koleksi ChromaDB |
| `MODEL_NAME` | `paraphrase-multilingual-MiniLM-L12-v2` | Model Sentence Transformer |
| `ABSTRAK_MAX_CHARS` | `300` | Batas karakter abstrak saat indexing |
| `ALLOWED_ORIGINS` | `http://localhost:8000` | CORS origins (pisah koma) |
| `SYNC_SECRET` | **(wajib diisi)** | Token auth untuk endpoint sync Laravel |
| `INFERENCE_CONCURRENCY` | `4` | Maks concurrent ML inference |
| `BULK_SYNC_CHUNK_SIZE` | `100` | Ukuran chunk untuk bulk-upsert |
| `LOG_LEVEL` | `INFO` | Level logging (DEBUG/INFO/WARNING/ERROR) |
| `HF_HUB_OFFLINE` | `0` | Set `1` di Docker (model sudah di-bake) |

> **Penting:** `SYNC_SECRET` wajib diisi dan minimal 16 karakter. Aplikasi **tidak akan start** jika kosong atau masih nilai default.

---

## Endpoint API

### Meta
| Method | Path | Keterangan |
|---|---|---|
| GET | `/` | Info service |
| GET | `/health` | Status health + statistik cache |

### Similarity (Rate-limited: 10 req/menit per IP)
| Method | Path | Keterangan |
|---|---|---|
| POST | `/api/v1/similarity/check` | Cek kemiripan judul dengan database |
| POST | `/api/v1/similarity/compare` | Bandingkan dua judul langsung |

**Contoh request `check`:**
```json
POST /api/v1/similarity/check
{
  "judul": "Sistem Deteksi Plagiarisme Menggunakan Machine Learning",
  "top_k": 5,
  "threshold": 0.5
}
```

**Contoh response:**
```json
{
  "query": { "judul": "Sistem Deteksi Plagiarisme..." },
  "total_found": 3,
  "results": [
    {
      "id": 42,
      "laravel_id": 100,
      "judul": "Deteksi Plagiat dengan Deep Learning",
      "similarity_score": 0.8921,
      "similarity_persen": "89.2%",
      "level": "SANGAT TINGGI"
    }
  ],
  "peringatan": "⚠️ Ditemukan judul dengan kemiripan SANGAT TINGGI (89.2%)..."
}
```

### Skripsi (Read-only + Delete)

> Data skripsi **hanya masuk melalui sinkronisasi Laravel** (`/sync`). Endpoint di bawah hanya untuk membaca dan manajemen data.

| Method | Path | Keterangan |
|---|---|---|
| GET | `/api/v1/skripsi` | Daftar skripsi (filter: `program_studi`, `tahun`, `limit`, `offset`) |
| GET | `/api/v1/skripsi/{id}` | Detail satu skripsi |
| DELETE | `/api/v1/skripsi/{id}` | Hapus skripsi berdasarkan ID internal |

### Sync dari Laravel 🔒
Semua endpoint sync memerlukan header:
```
Authorization: Bearer <SYNC_SECRET>
```

| Method | Path | Keterangan |
|---|---|---|
| POST | `/api/v1/sync/upsert` | Upsert satu skripsi (dari Observer) |
| POST | `/api/v1/sync/bulk-upsert` | Bulk upsert (202 Accepted — async) |
| DELETE | `/api/v1/sync/{laravel_id}` | Hapus berdasarkan laravel_id |

> **Catatan bulk-upsert:** Endpoint mengembalikan `202 Accepted` segera. Proses embedding dan indexing berjalan di **background task** agar tidak memblokir response Laravel.

---

## Deployment dengan Docker

### Build & Run

```bash
# Build image (model ML di-download saat build, tidak saat run)
docker compose build

# Jalankan
docker compose up -d

# Cek log
docker compose logs -f similarity-api

# Health check
curl http://localhost:8181/health
```

### Detail Dockerfile (Multi-Stage)

```
Stage 1 (builder):
  - Install semua Python dependencies
  - Download model ML ke /model_cache
  - Ukuran: ~3GB

Stage 2 (runtime):
  - Copy hanya packages + model dari builder
  - Non-root user (uid 1001)
  - Ukuran image final: ~1.5GB
```

### Resource yang Direkomendasikan

| Resource | Minimum | Produksi |
|---|---|---|
| RAM | 1 GB | 2 GB |
| CPU | 1 core | 2 core |
| Storage | 2 GB | 5 GB |

---

## Optimasi ONNX (Opsional)

Untuk performa inferensi 2-3× lebih cepat di CPU, konversi model ke ONNX:

```bash
# Konversi model ke ONNX
optimum-cli export onnx \
  --model paraphrase-multilingual-MiniLM-L12-v2 \
  --task feature-extraction \
  ./models_onnx

# Restart server — akan otomatis mendeteksi dan menggunakan ONNX
python main.py
```

---

## Scripts Utilitas

| Script | Kegunaan |
|---|---|
| `scripts/reindex.py` | Re-index ulang semua data ke ChromaDB (saat ganti model atau ChromaDB corrupt) |
| `scripts/optimize_model.py` | Konversi model ke ONNX untuk performa inferensi lebih cepat |

```bash
# Re-index semua data setelah ganti model embedding
python scripts/reindex.py --token <SYNC_SECRET> --batch-size 100

# Konversi model ke ONNX (jalankan sekali, lalu restart server)
python scripts/optimize_model.py
```

---

### `.env` Laravel
```env
SIMILARITY_API_URL=http://localhost:8181
SIMILARITY_API_SECRET=<nilai SYNC_SECRET yang sama di .env Python>
```

### Contoh Observer Laravel
```php
class SkripsiObserver
{
    public function saved(Skripsi $skripsi): void
    {
        Http::withToken(config('services.similarity.secret'))
            ->post(config('services.similarity.url') . '/api/v1/sync/upsert', [
                'laravel_id'     => $skripsi->id,
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

---

## Keamanan

| Fitur | Implementasi |
|---|---|
| Auth endpoint sync | Bearer Token (SYNC_SECRET, min 16 char) |
| Rate limiting | SlowAPI: 10 req/menit /similarity/check |
| CORS | Whitelist origin, method, dan header |
| SQL Injection | Tidak ada raw SQL — semua via SQLAlchemy ORM |
| Validasi input | Pydantic v2 dengan constraint (min_length, ge, le) |
| Secret validation | App GAGAL START jika SYNC_SECRET kosong/default |
| Non-root container | Docker berjalan sebagai uid 1001 |

---

## Monitoring

**Health check endpoint:**
```bash
curl http://localhost:8181/health
```
```json
{
  "status": "healthy",
  "model_loaded": true,
  "model_name": "paraphrase-multilingual-MiniLM-L12-v2",
  "model_backend": "sentence-transformers",
  "total_indexed": 312,
  "embedding_cache": {
    "size": 45,
    "maxsize": 1024,
    "currsize": 45
  }
}
```

---

## Pengembangan

```bash
# Format kode
pip install black isort
black . && isort .

# Jalankan dengan auto-reload
uvicorn main:app --reload --port 8181

# Cek apakah ada blocking code
# Semua ChromaDB call di vector_store.py menggunakan run_in_executor
# Semua ML inference di embedding_service.py menggunakan run_in_executor + semaphore
```
