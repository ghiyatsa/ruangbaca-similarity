#!/usr/bin/env python3
"""
Evaluasi akurasi model similarity menggunakan ground-truth pasangan judul.

Cara kerja:
  1. Membaca dataset evaluasi (JSON) yang berisi pasangan judul + label ground-truth
     (mirip=1, tidak_mirip=0).
  2. Memanggil endpoint /api/v1/similarity/compare untuk setiap pasang judul.
  3. Menghitung Precision, Recall, F1-Score, dan Accuracy pada berbagai threshold.
  4. Menyimpan hasil ke file JSON dan CSV untuk divisualisasikan di notebook.

Contoh penggunaan:
  python scripts/evaluate.py --token <SYNC_SECRET>
  python scripts/evaluate.py --token <SYNC_SECRET> --threshold 0.65 --output results/eval.json
  python scripts/evaluate.py --token <SYNC_SECRET> --dataset data/eval_dataset.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Dataset ground-truth bawaan (digunakan jika --dataset tidak diberikan)
# Pasangan judul nyata dari domain skripsi Informatika, diberi label:
#   1 = mirip / duplikat (positif)
#   0 = tidak mirip (negatif)
# ---------------------------------------------------------------------------
BUILTIN_DATASET = [
    # ----- POSITIF (mirip) -----
    {
        "judul_a": "Implementasi Algoritma K-Nearest Neighbor untuk Klasifikasi Penyakit Diabetes",
        "judul_b": "Penerapan Metode K-Nearest Neighbor dalam Klasifikasi Diabetes Mellitus",
        "label": 1,
    },
    {
        "judul_a": "Sistem Informasi Manajemen Perpustakaan Berbasis Web",
        "judul_b": "Rancang Bangun Sistem Informasi Perpustakaan Berbasis Web",
        "label": 1,
    },
    {
        "judul_a": "Deteksi Penyakit Tanaman Padi Menggunakan Convolutional Neural Network",
        "judul_b": "Klasifikasi Penyakit Pada Tanaman Padi Berbasis CNN",
        "label": 1,
    },
    {
        "judul_a": "Aplikasi Monitoring Kehadiran Mahasiswa Berbasis Android",
        "judul_b": "Sistem Absensi Mahasiswa Menggunakan Aplikasi Mobile Android",
        "label": 1,
    },
    {
        "judul_a": "Sistem Rekomendasi Film Menggunakan Collaborative Filtering",
        "judul_b": "Implementasi Collaborative Filtering untuk Rekomendasi Film",
        "label": 1,
    },
    {
        "judul_a": "Analisis Sentimen Ulasan Produk E-commerce Menggunakan Naive Bayes",
        "judul_b": "Klasifikasi Sentimen Review Toko Online dengan Metode Naive Bayes",
        "label": 1,
    },
    {
        "judul_a": "Prediksi Harga Rumah Menggunakan Algoritma Random Forest",
        "judul_b": "Peramalan Harga Properti Berbasis Random Forest Regression",
        "label": 1,
    },
    {
        "judul_a": "Sistem Deteksi Wajah Menggunakan Metode Viola-Jones",
        "judul_b": "Implementasi Face Detection dengan Algoritma Viola-Jones",
        "label": 1,
    },
    {
        "judul_a": "Rancang Bangun Aplikasi Point of Sale Berbasis Web untuk UMKM",
        "judul_b": "Pengembangan Sistem Kasir Point of Sale Berbasis Website untuk Usaha Kecil Menengah",
        "label": 1,
    },
    {
        "judul_a": "Optimasi Rute Pengiriman Menggunakan Algoritma Dijkstra",
        "judul_b": "Penerapan Algoritma Dijkstra untuk Pencarian Rute Terpendek pada Sistem Logistik",
        "label": 1,
    },
    # ----- NEGATIF (tidak mirip) -----
    {
        "judul_a": "Implementasi Blockchain untuk Keamanan Data Rekam Medis",
        "judul_b": "Sistem Rekomendasi Musik Menggunakan Collaborative Filtering",
        "label": 0,
    },
    {
        "judul_a": "Analisis Performa Algoritma Sorting pada Big Data",
        "judul_b": "Desain Antarmuka Aplikasi Mobile untuk Manajemen Keuangan",
        "label": 0,
    },
    {
        "judul_a": "Pendeteksian Hoaks di Media Sosial Menggunakan LSTM",
        "judul_b": "Sistem Informasi Geografis untuk Pemetaan Lokasi UMKM",
        "label": 0,
    },
    {
        "judul_a": "Implementasi Internet of Things untuk Sistem Smart Home",
        "judul_b": "Klasifikasi Teks Berita Menggunakan Support Vector Machine",
        "label": 0,
    },
    {
        "judul_a": "Pengembangan Game Edukasi Matematika untuk Siswa SD",
        "judul_b": "Analisis Kualitas Air Sungai Menggunakan Sensor IoT",
        "label": 0,
    },
    {
        "judul_a": "Sistem Pemantauan Cuaca Real-time Berbasis IoT",
        "judul_b": "Rancang Bangun Aplikasi E-Learning untuk Madrasah",
        "label": 0,
    },
    {
        "judul_a": "Penerapan Transfer Learning untuk Klasifikasi Citra Batik",
        "judul_b": "Sistem Manajemen Inventory Gudang Berbasis RFID",
        "label": 0,
    },
    {
        "judul_a": "Enkripsi Data Menggunakan Algoritma AES-256",
        "judul_b": "Prediksi Curah Hujan Menggunakan Artificial Neural Network",
        "label": 0,
    },
    {
        "judul_a": "Pengembangan Chatbot Layanan Pelanggan Menggunakan NLP",
        "judul_b": "Simulasi Jaringan Komputer dengan Cisco Packet Tracer",
        "label": 0,
    },
    {
        "judul_a": "Visualisasi Data COVID-19 di Indonesia Menggunakan D3.js",
        "judul_b": "Implementasi Fingerprint Authentication pada Sistem Absensi",
        "label": 0,
    },
    # ----- BORDERLINE -----
    {
        "judul_a": "Sistem Informasi Akademik Berbasis Web",
        "judul_b": "Aplikasi Pengolahan Data Nilai Mahasiswa Berbasis Website",
        "label": 1,
    },
    {
        "judul_a": "Deteksi Objek pada Citra Menggunakan YOLO",
        "judul_b": "Klasifikasi Gambar Menggunakan Convolutional Neural Network",
        "label": 0,
    },
]


def precision_recall_f1(tp: int, fp: int, fn: int):
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return round(precision, 4), round(recall, 4), round(f1, 4)


def evaluate_at_threshold(predictions: list, threshold: float) -> dict:
    tp = fp = fn = tn = 0
    for p in predictions:
        pred_label = 1 if p["score"] >= threshold else 0
        true_label = p["label"]
        if pred_label == 1 and true_label == 1:
            tp += 1
        elif pred_label == 1 and true_label == 0:
            fp += 1
        elif pred_label == 0 and true_label == 1:
            fn += 1
        else:
            tn += 1

    precision, recall, f1 = precision_recall_f1(tp, fp, fn)
    total = tp + fp + fn + tn
    accuracy = round((tp + tn) / total, 4) if total > 0 else 0.0

    return {
        "threshold": round(threshold, 2),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
    }


def run_evaluation(
    api_url: str,
    token: str,
    dataset: list,
    output_path,
    target_threshold: float,
    delay: float = 0.2,
) -> None:
    base = api_url.rstrip("/")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    print("Menghubungi API...")
    try:
        health = session.get(f"{base}/health", timeout=10).json()
        print(f"  API online - model: {health.get('model_name', '?')}")
        print(f"  Total terindeks: {health.get('total_indexed', '?')} dokumen")
        print(f"  Backend: {health.get('model_backend', '?')}\n")
    except Exception as exc:
        print(f"  Tidak bisa terhubung ke API: {exc}")
        sys.exit(1)

    print(f"Mengevaluasi {len(dataset)} pasang judul...")
    predictions = []

    for i, item in enumerate(dataset, 1):
        judul_a = item["judul_a"]
        judul_b = item["judul_b"]
        true_label = item["label"]

        try:
            resp = session.post(
                f"{base}/api/v1/similarity/compare",
                params={"judul_a": judul_a, "judul_b": judul_b},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            score = data.get("similarity_score", 0.0)
            semantic = data.get("detail", {}).get("semantic_score", 0.0)
            lexical = data.get("detail", {}).get("lexical_score", 0.0)
            level = data.get("level", "-")
        except Exception as exc:
            print(f"  [{i:02d}] GAGAL: {exc}")
            score = 0.0
            semantic = 0.0
            lexical = 0.0
            level = "ERROR"

        pred_label = 1 if score >= target_threshold else 0
        status = "OK" if pred_label == true_label else "SALAH"
        print(
            f"  [{i:02d}] {status} score={score:.3f} "
            f"(sem={semantic:.3f}, jac={lexical:.3f}) "
            f"label={true_label} pred={pred_label} | {judul_a[:45]}..."
        )

        predictions.append({
            "no": i,
            "judul_a": judul_a,
            "judul_b": judul_b,
            "label": true_label,
            "score": score,
            "semantic_score": semantic,
            "lexical_score": lexical,
            "level": level,
        })
        time.sleep(delay)

    thresholds = [round(t / 100, 2) for t in range(40, 96, 5)]
    metrics_by_threshold = [evaluate_at_threshold(predictions, t) for t in thresholds]

    best = max(metrics_by_threshold, key=lambda x: x["f1"])
    target_metrics = evaluate_at_threshold(predictions, target_threshold)

    print(f"\n{'=' * 55}")
    print("  HASIL EVALUASI")
    print(f"{'=' * 55}")
    print(f"  Total pasangan   : {len(dataset)}")
    print(f"  Threshold target : {target_threshold}")
    print(f"  Precision        : {target_metrics['precision']:.4f}")
    print(f"  Recall           : {target_metrics['recall']:.4f}")
    print(f"  F1-Score         : {target_metrics['f1']:.4f}")
    print(f"  Accuracy         : {target_metrics['accuracy']:.4f}")
    print(f"  TP={target_metrics['tp']} FP={target_metrics['fp']} "
          f"FN={target_metrics['fn']} TN={target_metrics['tn']}")
    print(f"\n  Threshold terbaik (F1): {best['threshold']} "
          f"-> F1={best['f1']:.4f} Precision={best['precision']:.4f} Recall={best['recall']:.4f}")
    print(f"{'=' * 55}\n")

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("results", exist_ok=True)
        output_path = f"results/eval_{timestamp}.json"

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    result_data = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "api_url": api_url,
            "total_pairs": len(dataset),
            "target_threshold": target_threshold,
            "best_threshold": best["threshold"],
            "model_name": health.get("model_name", "unknown"),
            "model_backend": health.get("model_backend", "unknown"),
        },
        "target_threshold_metrics": target_metrics,
        "best_threshold_metrics": best,
        "metrics_by_threshold": metrics_by_threshold,
        "predictions": predictions,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    print(f"Hasil disimpan ke: {output_path}")

    csv_path = output_path.replace(".json", "_threshold_sweep.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["threshold", "tp", "fp", "fn", "tn",
                           "precision", "recall", "f1", "accuracy"]
        )
        writer.writeheader()
        writer.writerows(metrics_by_threshold)
    print(f"Threshold sweep disimpan ke: {csv_path}")

    pred_csv = output_path.replace(".json", "_predictions.csv")
    with open(pred_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["no", "judul_a", "judul_b", "label", "score",
                           "semantic_score", "lexical_score", "level"]
        )
        writer.writeheader()
        writer.writerows(predictions)
    print(f"Detail prediksi disimpan ke: {pred_csv}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluasi akurasi model semantic similarity RuangBaca"
    )
    parser.add_argument("--url", default="http://localhost:8181",
                        help="Base URL API (default: http://localhost:8181)")
    parser.add_argument("--token", required=True,
                        help="SYNC_SECRET dari .env")
    parser.add_argument("--threshold", type=float, default=0.65,
                        help="Threshold similarity (default: 0.65)")
    parser.add_argument("--dataset", default=None,
                        help="Path file JSON dataset kustom (opsional)")
    parser.add_argument("--output", default=None,
                        help="Path output JSON (default: results/eval_<timestamp>.json)")
    parser.add_argument("--delay", type=float, default=0.2,
                        help="Jeda antar request detik (default: 0.2)")
    args = parser.parse_args()

    if args.dataset:
        try:
            with open(args.dataset, "r", encoding="utf-8") as f:
                dataset = json.load(f)
            print(f"Dataset dimuat dari: {args.dataset} ({len(dataset)} pasang)\n")
        except Exception as exc:
            print(f"Gagal membaca dataset: {exc}")
            sys.exit(1)
    else:
        dataset = BUILTIN_DATASET
        print(f"Menggunakan dataset bawaan ({len(dataset)} pasang)\n")

    run_evaluation(
        api_url=args.url,
        token=args.token,
        dataset=dataset,
        output_path=args.output,
        target_threshold=args.threshold,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
