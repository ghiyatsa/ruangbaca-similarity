#!/usr/bin/env python3
"""
Script pengujian akurasi pencarian (Search Retrieval Accuracy).
Menguji seberapa baik sistem menemukan dokumen target (1 vs N) dari kueri baru
berdasarkan seluruh database vektor yang sudah terindeks di ChromaDB.
"""
import argparse
import csv
import sys
import requests

def run_search_evaluation(api_url: str, token: str, csv_path: str, threshold: float = 0.5):
    base = api_url.rstrip("/")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    print(f"============================================================")
    # 1. Cek koneksi & jumlah data terindeks
    try:
        health = session.get(f"{base}/health", timeout=5).json()
        total_indexed = health.get("total_indexed", 0)
        print(f"API Terkoneksi : {health.get('status')}")
        print(f"Total Indeks   : {total_indexed} dokumen")
        print(f"Model Aktif    : {health.get('model_name')}")
        if total_indexed == 0:
            print("Error: Database vektor kosong. Silakan jalankan scripts/index_csv.py terlebih dahulu.")
            sys.exit(1)
    except Exception as exc:
        print(f"Gagal menghubungkan ke API: {exc}")
        sys.exit(1)

    # 2. Muat dataset uji pencarian
    queries = []
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                queries.append({
                    "query_judul": row["query_judul"].strip(),
                    "expected_document_id": row["expected_document_id"].strip()
                })
        print(f"Berhasil memuat {len(queries)} kueri uji dari {csv_path}")
    except Exception as exc:
        print(f"Gagal membaca file CSV: {exc}")
        sys.exit(1)

    print(f"============================================================")
    print(f"MEMULAI EVALUASI RETRIEVAL (Threshold={threshold})")
    print(f"============================================================\n")

    top_1_hits = 0
    top_5_hits = 0
    failures = 0

    print(f"{'No':<3} | {'Kueri':<45} | {'Target':<18} | {'Hasil Rank':<10}")
    print(f"-" * 85)

    for idx, q in enumerate(queries, start=1):
        query_text = q["query_judul"]
        expected_id = q["expected_document_id"]
        
        # Ekstrak tipe dokumen berdasarkan expected_id prefix (skripsi_ atau internship_report_)
        doc_type = "skripsi" if expected_id.startswith("skripsi_") else "internship_report"

        try:
            # Panggil endpoint check similarity
            response = session.post(
                f"{base}/api/v1/similarity/check",
                json={
                    "judul": query_text,
                    "top_k": 5,
                    "threshold": threshold,
                    "document_type": doc_type
                },
                timeout=10
            )
            response.raise_for_status()
            res_data = response.json()
            results = res_data.get("results", [])
        except Exception as exc:
            print(f"{idx:<3} | {query_text[:42]+'...':<45} | {expected_id:<18} | ERROR: {exc}")
            failures += 1
            continue

        # Cari ranking expected_id di hasil retrieval
        found_rank = -1
        for rank, item in enumerate(results, start=1):
            if item["id"] == expected_id:
                found_rank = rank
                break

        rank_str = "Miss (Not Found)"
        if found_rank != -1:
            rank_str = f"Rank {found_rank}"
            top_5_hits += 1
            if found_rank == 1:
                top_1_hits += 1

        print(f"{idx:<3} | {query_text[:42]+'...':<45} | {expected_id:<18} | {rank_str:<10}")

    total_valid = len(queries) - failures
    hit_rate_1 = (top_1_hits / total_valid) * 100 if total_valid > 0 else 0.0
    hit_rate_5 = (top_5_hits / total_valid) * 100 if total_valid > 0 else 0.0

    print(f"\n============================================================")
    print(f"METRIK EVALUASI RETRIEVAL SISTEM (PENCARIAN)")
    print(f"============================================================")
    print(f"Database Scope    : {total_indexed} total dokumen")
    print(f"Jumlah Kueri Uji  : {len(queries)}")
    print(f"Sukses Terpanggil : {total_valid}")
    print(f"Top-1 Hits (Rank 1): {top_1_hits}")
    print(f"Top-5 Hits (Rank 1-5): {top_5_hits}")
    print(f"-" * 45)
    print(f"Top-1 Accuracy (Hit Rate @1) : {hit_rate_1:.1f}%")
    print(f"Top-5 Accuracy (Hit Rate @5) : {hit_rate_5:.1f}%")
    print(f"============================================================\n")
    print("Selesai! Nilai Hit Rate ini merepresentasikan akurasi penemuan dokumen duplikat di database.")

def main():
    parser = argparse.ArgumentParser(
        description="Script Pengujian Akurasi Retrieval 1 vs N pada Database Vektor"
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
        "--csv",
        required=True,
        help="Path ke file CSV dataset uji pencarian (contoh: data/eval-search-skripsi.csv)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.50,
        help="Batas minimum nilai cosine similarity (default: 0.50)",
    )
    args = parser.parse_args()
    run_search_evaluation(args.url, args.token, args.csv, args.threshold)

if __name__ == "__main__":
    main()
