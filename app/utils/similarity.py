"""
Helper untuk mengklasifikasikan skor kemiripan ke dalam label level.
"""


def get_similarity_level(score: float) -> str:
    """
    Konversi skor cosine similarity (0.0 – 1.0) ke label level.

    | Level         | Skor      | Rekomendasi              |
    |---------------|-----------|--------------------------|
    | SANGAT TINGGI | ≥ 85 %    | Wajib revisi judul/topik |
    | TINGGI        | 70 – 84 % | Pertimbangkan revisi     |
    | SEDANG        | 50 – 69 % | Perlu ditinjau           |
    | RENDAH        | < 50 %    | Aman                     |
    """
    if score >= 0.85:
        return "SANGAT TINGGI"
    elif score >= 0.70:
        return "TINGGI"
    elif score >= 0.50:
        return "SEDANG"
    else:
        return "RENDAH"


def format_persen(score: float) -> str:
    """Konversi skor float ke string persen dengan 1 desimal."""
    return f"{score * 100:.1f}%"
