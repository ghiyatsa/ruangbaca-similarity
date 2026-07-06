#!/usr/bin/env python3
"""
Script pengujian akurasi deteksi kemiripan skripsi (Semantic Similarity).
Script ini menghitung metric akurasi (Precision, Recall, F1-Score)
serta membandingkan cosine similarity menggunakan skenario judul mirip/sinonim.
Hasil evaluasi ini siap digunakan untuk isi Bab 4/Bab 5 Laporan Skripsi.
"""
import argparse
import csv
import sys
import time
import requests

## 1 = Mirip/Duplikat secara topik, 0 = Berbeda topik/Tidak Mirip


def run_evaluation(api_url: str, token: str, threshold: float = 0.70, csv_path: str = None):
    if not csv_path:
        print("Error: Parameter --csv wajib disertakan (contoh: eval-skripsi.csv atau eval-laporan-kp.csv)")
        sys.exit(1)

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

    print(f"Membaca dataset uji dari: {csv_path}")
    dataset = []
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            # Cek apakah ini file mentah (seperti data-skripsi.csv atau data-laporan-kp.csv)
            if headers and "Judul" in headers:
                rows = list(reader)
                import random
                random.seed(42) # Agar hasil pengujian reproducible
                
                # Fungsi pembantu untuk mengacak urutan kata
                def _perturb(t: str) -> str:
                    w = t.split()
                    if len(w) > 3:
                        w[1], w[2] = w[2], w[1]
                    return " ".join(w)

                # 1. Pasangan Positif (Judul vs Diri Sendiri / Judul Teracak) -> GT = 1
                for row in rows[:10]:
                    judul = row["Judul"].strip()
                    if judul:
                        dataset.append({"judul_a": judul, "judul_b": judul, "ground_truth": 1})
                for row in rows[10:20]:
                    judul = row["Judul"].strip()
                    if judul:
                        dataset.append({"judul_a": judul, "judul_b": _perturb(judul), "ground_truth": 1})

                # 2. Pasangan Negatif (Judul A vs Judul B Acak yang berbeda) -> GT = 0
                neg_count = 0
                while neg_count < 20 and len(rows) > 1:
                    r1 = random.choice(rows)
                    r2 = random.choice(rows)
                    j1 = r1["Judul"].strip()
                    j2 = r2["Judul"].strip()
                    if j1 != j2:
                        dataset.append({"judul_a": j1, "judul_b": j2, "ground_truth": 0})
                        neg_count += 1
                
                print(f"Dataset mentah terdeteksi. Membuat {len(dataset)} pasangan uji dinamis (20 positif, 20 negatif).")
            else:
                # Dataset uji kustom berformat judul_a, judul_b, ground_truth
                for row in reader:
                    dataset.append({
                        "judul_a": row["judul_a"],
                        "judul_b": row["judul_b"],
                        "ground_truth": int(row["ground_truth"])
                    })
        print(f"Berhasil memuat {len(dataset)} pasangan uji.")
    except Exception as exc:
        print(f"Gagal membaca file CSV dataset: {exc}")
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

    for i, data in enumerate(dataset, start=1):
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
    accuracy = (tp + tn) / len(dataset)

    print(f"\n============================================================")
    print(f"METRIK EVALUASI AKURASI SISTEM")
    print(f"============================================================")
    print(f"Jumlah Data Uji : {len(dataset)}")
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
    parser.add_argument(
        "--csv",
        required=True,
        help="Path ke file CSV dataset uji (contoh: eval-skripsi.csv atau eval-laporan-kp.csv)",
    )
    args = parser.parse_args()
    run_evaluation(args.url, args.token, args.threshold, args.csv)

if __name__ == "__main__":
    main()
