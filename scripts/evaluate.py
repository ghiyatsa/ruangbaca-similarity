#!/usr/bin/env python3
"""
Script pengujian akurasi deteksi kemiripan skripsi (Semantic Similarity).
Script ini menghitung metric akurasi (Precision, Recall, F1-Score)
serta membandingkan cosine similarity menggunakan skenario judul mirip/sinonim.
Hasil evaluasi ini siap digunakan untuk isi Bab 4/Bab 5 Laporan Skripsi.
"""
import argparse
import sys
import time
import requests

# Dataset uji evaluasi (Judul A, Judul B, Label Kemiripan Sebenarnya/Ground Truth)
# 1 = Mirip/Duplikat secara topik, 0 = Berbeda topik/Tidak Mirip
TEST_DATASET = [
    # Pasangan Judul Mirip (Sinonim / Parafrase) - Harus dideteksi tinggi
    {
        "judul_a": "Penerapan Algoritma K-Means untuk Klasterisasi Data Mahasiswa",
        "judul_b": "Klasterisasi Mahasiswa Menggunakan Metode K-Means",
        "ground_truth": 1
    },
    {
        "judul_a": "Sistem Rekomendasi Wisata dengan Metode Collaborative Filtering",
        "judul_b": "Implementasi Collaborative Filtering Pada Sistem Rekomendasi Tempat Wisata",
        "ground_truth": 1
    },
    {
        "judul_a": "Analisis Sentimen Opini Publik Menggunakan Naive Bayes Classifier",
        "judul_b": "Klasifikasi Sentimen Opini Masyarakat dengan Metode Naive Bayes",
        "ground_truth": 1
    },
    {
        "judul_a": "Rancang Bangun Aplikasi E-Commerce Berbasis Mobile Android",
        "judul_b": "Pengembangan Aplikasi Penjualan Online Menggunakan Android Mobile",
        "ground_truth": 1
    },
    {
        "judul_a": "Sistem Deteksi Penyakit Padi Menggunakan Convolutional Neural Network",
        "judul_b": "Klasifikasi Citra Penyakit Tanaman Padi Berbasis CNN",
        "ground_truth": 1
    },
    # Pasangan Judul Berbeda (Negatif Palsu) - Harus dideteksi rendah
    {
        "judul_a": "Sistem Rekomendasi Wisata dengan Metode Collaborative Filtering",
        "judul_b": "Analisis Sentimen Opini Publik Menggunakan Naive Bayes Classifier",
        "ground_truth": 0
    },
    {
        "judul_a": "Klasifikasi Citra Penyakit Tanaman Padi Berbasis CNN",
        "judul_b": "Implementasi K-Means untuk Pengelompokan Tingkat Kemiskinan",
        "ground_truth": 0
    },
    {
        "judul_a": "Rancang Bangun Aplikasi E-Commerce Berbasis Mobile Android",
        "judul_b": "Analisis Perbandingan Kecepatan Algoritma Sorting pada Java",
        "ground_truth": 0
    },
    {
        "judul_a": "Penerapan Algoritma K-Means untuk Klasterisasi Data Mahasiswa",
        "judul_b": "Pengembangan Game Edukasi Pengenalan Huruf Hijaiyah Menggunakan Unity",
        "ground_truth": 0
    },
    {
        "judul_a": "Sistem Deteksi Penyakit Padi Menggunakan Convolutional Neural Network",
        "judul_b": "Rancang Bangun Sistem Keamanan Jaringan Menggunakan Firewall",
        "ground_truth": 0
    }
]

def run_evaluation(api_url: str, token: str, threshold: float = 0.70):
    base = api_url.rstrip("/")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    print(f"============================================================")
    # 1. Cek koneksi API
    try:
        health = session.get(f"{base}/health", timeout=5).json()
        print(f"API Terkoneksi: {health.get('status')}")
        print(f"Model Aktif   : {health.get('model_name')}")
        print(f"Backend       : {health.get('model_backend')}")
    except Exception as exc:
        print(f"Gagal menghubungkan ke API: {exc}")
        sys.exit(1)
    
    print(f"============================================================")
    print(f"MEMULAI EVALUASI AKURASI DENGAN THRESHOLD = {threshold}")
    print(f"============================================================\n")

    tp = 0 # True Positive
    fp = 0 # False Positive
    tn = 0 # True Negative
    fn = 0 # False Negative

    print(f"{'No':<3} | {'Skor':<6} | {'Prediksi':<8} | {'GroundTruth':<11} | {'Hasil Evaluasi':<15}")
    print(f"-" * 70)

    for i, data in enumerate(TEST_DATASET, start=1):
        try:
            response = session.post(
                f"{base}/api/v1/similarity/compare",
                params={"judul_a": data["judul_a"], "judul_b": data["judul_b"]},
                timeout=10
            )
            response.raise_for_status()
            res_data = response.json()
            score = res_data["similarity_score"]
        except Exception as exc:
            print(f"Error pada pengujian ke-{i}: {exc}")
            continue

        # Prediksi sistem berdasarkan threshold
        prediction = 1 if score >= threshold else 0
        gt = data["ground_truth"]

        status = ""
        if prediction == 1 and gt == 1:
            tp += 1
            status = "True Positive (TP)"
        elif prediction == 1 and gt == 0:
            fp += 1
            status = "False Positive (FP)"
        elif prediction == 0 and gt == 0:
            tn += 1
            status = "True Negative (TN)"
        elif prediction == 0 and gt == 1:
            fn += 1
            status = "False Negative (FN)"

        print(f"{i:<3} | {score:<6.4f} | {prediction:<8} | {gt:<11} | {status:<15}")
        
    # Perhitungan Metrik Akurasi
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (tp + tn) / len(TEST_DATASET)

    print(f"\n============================================================")
    print(f"METRIK EVALUASI AKURASI SISTEM")
    print(f"============================================================")
    print(f"Jumlah Data Uji : {len(TEST_DATASET)}")
    print(f"True Positive   : {tp}")
    print(f"False Positive  : {fp}")
    print(f"True Negative   : {tn}")
    print(f"False Negative  : {fn}")
    print(f"-" * 45)
    print(f"Akurasi (Accuracy)   : {accuracy * 100:.1f}%")
    print(f"Presisi (Precision)  : {precision * 100:.1f}%")
    print(f"Recall (Sensitivitas): {recall * 100:.1f}%")
    print(f"F1-Score             : {f1_score * 100:.1f}%")
    print(f"============================================================\n")
    print("Selesai! Hasil metrik di atas dapat dimasukkan ke Bab Pengujian Laporan Skripsi.")

def main():
    parser = argparse.ArgumentParser(
        description="Script Pengujian Akurasi Model Semantic Similarity Skripsi"
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
        "--threshold",
        type=float,
        default=0.70,
        help="Batas minimum nilai cosine similarity untuk dikatakan mirip (default: 0.70)",
    )
    args = parser.parse_args()
    run_evaluation(args.url, args.token, args.threshold)

if __name__ == "__main__":
    main()
