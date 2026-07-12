"""
Konfigurasi sistem pencatatan terstruktur (structured logging).
Menggantikan fungsi keluaran standar untuk memfasilitasi pemformatan dan penyaringan log.
"""
import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Konfigurasi root logger dengan format yang konsisten."""
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
