"""
Structured logging setup.
Ganti semua `print()` dengan logger agar output bisa di-filter dan di-format.
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
    # Kurangi noise dari library eksternal
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
