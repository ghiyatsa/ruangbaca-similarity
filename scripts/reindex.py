#!/usr/bin/env python3
"""
Re-index ulang semua data dari SQLite ke ChromaDB.

Berguna saat:
- Mengganti model embedding
- ChromaDB corrupt atau terhapus
- Migrasi ke server baru

Cara kerja:
1. Ambil semua data dari endpoint GET /api/v1/skripsi dengan paginasi.
2. Kirim ulang ke endpoint POST /api/v1/sync/bulk-upsert.
3. Semua data diasumsikan sudah memiliki skripsi_id dari sistem sumber.
"""
import argparse
import sys
import time

import requests


def reindex_all(api_url: str, token: str, batch_size: int = 100) -> None:
    base = api_url.rstrip("/")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    try:
        health = session.get(f"{base}/health", timeout=5).json()
        print(f"API online - total terindeks saat ini: {health.get('total_indexed', '?')}")
    except Exception as exc:
        print(f"Tidak bisa terhubung ke API: {exc}")
        sys.exit(1)

    print(f"Memulai re-indexing (batch_size={batch_size})...\n")

    offset = 0
    batch_num = 0
    total_success = 0
    total_failed = 0

    while True:
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
            break

        batch_num += 1
        print(f"Batch {batch_num}: {len(batch)} item (offset {offset})")

        with_source_id = [record for record in batch if record.get("skripsi_id")]
        skipped = len(batch) - len(with_source_id)
        if skipped:
            print(f"  Lewati {skipped} item tanpa skripsi_id")

        if with_source_id:
            payload = [
                {
                    "skripsi_id": record["skripsi_id"],
                    "judul": record["judul"],
                    "abstrak": record.get("abstrak"),
                    "kata_kunci": record.get("kata_kunci"),
                    "tahun": record.get("tahun"),
                    "program_studi": record.get("program_studi"),
                    "nim": record.get("nim"),
                    "nama_mahasiswa": record.get("nama_mahasiswa"),
                }
                for record in with_source_id
            ]

            try:
                res = session.post(
                    f"{base}/api/v1/sync/bulk-upsert",
                    json={"data": payload},
                    timeout=30,
                )
                res.raise_for_status()
                total_success += len(with_source_id)
                print(f"  Batch {batch_num} diterima (202 Accepted - diproses di background)")
            except Exception as exc:
                total_failed += len(with_source_id)
                print(f"  Batch {batch_num} gagal: {exc}")

        offset += batch_size
        time.sleep(0.5)

    print(f"\n{'=' * 45}")
    print("  Re-indexing selesai")
    print(f"  Berhasil dikirim : {total_success}")
    print(f"  Gagal            : {total_failed}")
    print(f"{'=' * 45}")
    print("Catatan: proses embedding berjalan di background API - cek /health untuk status.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-index ulang semua skripsi dari SQLite ke ChromaDB"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8181",
        help="URL API (default: http://localhost:8181)",
    )
    parser.add_argument(
        "--token",
        required=True,
        help="SYNC_SECRET dari .env untuk autentikasi",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Jumlah item per batch (default: 100)",
    )
    args = parser.parse_args()
    reindex_all(args.url, args.token, args.batch_size)


if __name__ == "__main__":
    main()
