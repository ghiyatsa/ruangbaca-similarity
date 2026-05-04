#!/usr/bin/env python3
"""
reindex.py — Re-index ulang semua data dari SQLite ke ChromaDB.

Berguna saat:
  - Mengganti model embedding (perlu rebuild semua vector)
  - ChromaDB corrupt atau terhapus
  - Migrasi ke server baru

Cara kerja:
  1. Ambil semua data dari endpoint GET /api/v1/skripsi (paginasi)
  2. Kirim ulang ke endpoint POST /api/v1/sync/bulk-upsert
  3. Semua data diasumsikan sudah memiliki laravel_id (masuk via Laravel sync)

Penggunaan:
  python scripts/reindex.py
  python scripts/reindex.py --url http://localhost:8181 --token <SYNC_SECRET>
"""
import argparse
import sys
import time

import requests


def reindex_all(api_url: str, token: str, batch_size: int = 100) -> None:
    base    = api_url.rstrip("/")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    # 1. Cek health
    try:
        health = session.get(f"{base}/health", timeout=5).json()
        print(f"API online — total terindeks saat ini: {health.get('total_indexed', '?')}")
    except Exception as exc:
        print(f"Tidak bisa terhubung ke API: {exc}")
        sys.exit(1)

    print(f"Memulai re-indexing (batch_size={batch_size})...\n")

    offset        = 0
    batch_num     = 0
    total_success = 0
    total_failed  = 0

    while True:
        # 2. Ambil batch data dari SQLite via API
        try:
            resp = session.get(
                f"{base}/api/v1/skripsi",
                params={"limit": batch_size, "offset": offset},
                timeout=30,
            )
            resp.raise_for_status()
            batch = resp.json()
        except Exception as exc:
            print(f"Gagal mengambil data (offset={offset}): {exc}")
            break

        if not batch:
            break  # Semua data sudah diproses

        batch_num += 1
        print(f"Batch {batch_num}: {len(batch)} item (offset {offset})")

        # Filter hanya yang punya laravel_id (data dari Laravel)
        with_laravel = [r for r in batch if r.get("laravel_id")]
        skipped      = len(batch) - len(with_laravel)
        if skipped:
            print(f"  Lewati {skipped} item tanpa laravel_id")

        if with_laravel:
            payload = [
                {
                    "laravel_id":    r["laravel_id"],
                    "judul":         r["judul"],
                    "abstrak":       r.get("abstrak"),
                    "kata_kunci":    r.get("kata_kunci"),
                    "tahun":         r.get("tahun"),
                    "program_studi": r.get("program_studi"),
                    "nim":           r.get("nim"),
                    "nama_mahasiswa": r.get("nama_mahasiswa"),
                }
                for r in with_laravel
            ]
            try:
                res = session.post(
                    f"{base}/api/v1/sync/bulk-upsert",
                    json={"data": payload},
                    timeout=30,  # 202 Accepted — tidak perlu tunggu lama
                )
                res.raise_for_status()
                total_success += len(with_laravel)
                print(f"  Batch {batch_num} diterima (202 Accepted — diproses di background)")
            except Exception as exc:
                total_failed += len(with_laravel)
                print(f"  Batch {batch_num} gagal: {exc}")

        offset += batch_size
        time.sleep(0.5)  # jeda agar background task sempat memproses

    print(f"\n{'═' * 45}")
    print(f"  Re-indexing selesai")
    print(f"  Berhasil dikirim : {total_success}")
    print(f"  Gagal            : {total_failed}")
    print(f"{'═' * 45}")
    print("Catatan: proses embedding berjalan di background API — cek /health untuk status.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-index ulang semua skripsi dari SQLite ke ChromaDB"
    )
    parser.add_argument(
        "--url", default="http://localhost:8181",
        help="URL API (default: http://localhost:8181)"
    )
    parser.add_argument(
        "--token", required=True,
        help="SYNC_SECRET dari .env untuk autentikasi"
    )
    parser.add_argument(
        "--batch-size", type=int, default=100,
        help="Jumlah item per batch (default: 100)"
    )
    args = parser.parse_args()
    reindex_all(args.url, args.token, args.batch_size)


if __name__ == "__main__":
    main()
