#!/usr/bin/env python3
"""
Script Benchmark Latensi API Deteksi Kemiripan.
Mengukur waktu respons endpoint /compare untuk analisis performa di Laporan KP/Skripsi.
"""
import argparse
import time
import requests
import statistics

def run_benchmark(api_url: str, token: str, iterations: int = 50):
    base = api_url.rstrip("/")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    judul_a = "Penerapan Algoritma K-Means untuk Klasterisasi Data Mahasiswa"
    judul_b = "Klasterisasi Mahasiswa Menggunakan Metode K-Means"

    print(f"============================================================")
    print(f"MEMULAI BENCHMARK LATENSI API SIMILARITY")
    print(f"============================================================")
    print(f"Target URL   : {base}")
    print(f"Iterasi      : {iterations} kali")
    
    # 1. Warm-up request
    try:
        session.post(
            f"{base}/api/v1/similarity/compare",
            params={"judul_a": judul_a, "judul_b": judul_b},
            timeout=10
        )
    except Exception as exc:
        print(f"Gagal menghubungkan ke API untuk benchmark: {exc}")
        return

    # 2. Main loop
    latencies = []
    for i in range(1, iterations + 1):
        start_time = time.perf_counter()
        try:
            response = session.post(
                f"{base}/api/v1/similarity/compare",
                params={"judul_a": judul_a, "judul_b": judul_b},
                timeout=10
            )
            response.raise_for_status()
            latency = (time.perf_counter() - start_time) * 1000 # ms
            latencies.append(latency)
            if i % 10 == 0 or i == iterations:
                print(f"Progress: {i}/{iterations} request selesai...")
        except Exception as exc:
            print(f"Gagal pada request ke-{i}: {exc}")
            continue

    if not latencies:
        print("Tidak ada data latensi yang berhasil dikumpulkan.")
        return

    # 3. Hitung Statistik
    avg_lat = statistics.mean(latencies)
    med_lat = statistics.median(latencies)
    min_lat = min(latencies)
    max_lat = max(latencies)
    std_dev = statistics.stdev(latencies) if len(latencies) > 1 else 0.0

    print(f"\n============================================================")
    print(f"HASIL ANALISIS LATENSI (SATUAN MILISEKON / MS)")
    print(f"============================================================")
    print(f"Total Sukses   : {len(latencies)}/{iterations}")
    print(f"Rata-rata      : {avg_lat:.2f} ms")
    print(f"Median         : {med_lat:.2f} ms")
    print(f"Minimum        : {min_lat:.2f} ms")
    print(f"Maksimum       : {max_lat:.2f} ms")
    print(f"Standar Deviasi: {std_dev:.2f} ms")
    print(f"============================================================")
    print("Angka di atas siap dimasukkan ke Bab Pengujian/Analisis Kinerja Laporan Anda.")

def main():
    parser = argparse.ArgumentParser(
        description="Script Benchmark Latensi API"
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
        "--iterations",
        type=int,
        default=50,
        help="Jumlah iterasi pengujian (default: 50)",
    )
    args = parser.parse_args()
    run_benchmark(args.url, args.token, args.iterations)

if __name__ == "__main__":
    main()
