#!/usr/bin/env python3
"""
Script pengindeksan massal dari file CSV ke ChromaDB via FastAPI Sync API.
Membaca data-skripsi.csv dan data-laporan-kp.csv, mengonversi ke format API,
lalu mengirimkannya ke endpoint bulk-upsert.
"""
import argparse
import csv
import sys
import time
import requests

def index_csv_file(file_path: str, doc_type: str, api_url: str, token: str, batch_size: int = 100):
    base = api_url.rstrip("/")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    print(f"------------------------------------------------------------")
    print(f"Membaca file: {file_path} (tipe: {doc_type})")
    
    records = []
    try:
        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Konversi tahun ke int jika valid
                try:
                    tahun = int(row.get("Tahun", 0))
                except (ValueError, TypeError):
                    tahun = 2024 # Default fallback

                records.append({
                    "document_id": f"{doc_type}_{row.get('No', '0')}",
                    "document_type": doc_type,
                    "judul": row.get("Judul", "").strip(),
                    "abstrak": row.get("Abstrak", "").strip(),
                    "kata_kunci": row.get("Kata Kunci", "").strip(),
                    "tahun": tahun,
                    "program_studi": "Informatika", # Default prodi
                    "nim": row.get("NIM", "").strip(),
                    "nama_mahasiswa": row.get("Nama", "").strip()
                })
    except Exception as exc:
        print(f"Gagal membaca file {file_path}: {exc}")
        return

    total_records = len(records)
    print(f"Total data ditemukan: {total_records} baris.")

    # Kirim dalam batch
    for i in range(0, total_records, batch_size):
        chunk = records[i:i + batch_size]
        print(f"Mengirim batch {i//batch_size + 1} ({len(chunk)} item, offset {i})...")
        try:
            response = session.post(
                f"{base}/api/v1/sync/bulk-upsert",
                json={"data": chunk, "reset_index": False},
                timeout=60
            )
            response.raise_for_status()
            res_data = response.json()
            print(f"  Status: Diterima (Job ID: {res_data.get('job_id')})")
        except Exception as exc:
            print(f"  Gagal mengirim batch: {exc}")
            
        time.sleep(1) # Delay singkat agar server tidak overload

def main():
    parser = argparse.ArgumentParser(
        description="Indeks ulang database lokal dari data-skripsi.csv dan data-laporan-kp.csv"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8181",
        help="URL API lokal (default: http://localhost:8181)",
    )
    parser.add_argument(
        "--token",
        required=True,
        help="SYNC_SECRET dari .env untuk autentikasi",
    )
    args = parser.parse_args()

    # Cek koneksi
    try:
        res = requests.get(f"{args.url.rstrip('/')}/health", timeout=5)
        res.raise_for_status()
        print(f"API Terkoneksi. Total terindeks saat ini: {res.json().get('total_indexed', 0)}")
    except Exception as exc:
        print(f"Gagal menghubungkan ke API di {args.url}: {exc}")
        sys.exit(1)

    # Indeks Skripsi
    index_csv_file("data/data-skripsi.csv", "skripsi", args.url, args.token)
    
    # Indeks Laporan KP
    index_csv_file("data/data-laporan-kp.csv", "internship_report", args.url, args.token)

    print(f"\n============================================================")
    print("Pengiriman data selesai! Proses embedding sedang berjalan di latar belakang (background).")
    print("Silakan pantau jumlah data terindeks dengan menembak:")
    print(f"GET {args.url.rstrip('/')}/health")
    print(f"============================================================")

if __name__ == "__main__":
    main()
