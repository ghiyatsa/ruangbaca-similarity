# ── Stage 1: Install Python dependencies ──────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install \
       torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

RUN groupadd --gid 1000 appgroup \
    && useradd --create-home --uid 1000 --gid appgroup appuser

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create persistent data directory (model cache, DB, chroma)
RUN mkdir -p /data /data/.huggingface /data/chroma_db /home/appuser/app \
    && chown -R appuser:appgroup /data /home/appuser/app

USER appuser
ENV HOME=/home/appuser \
    PATH=/home/appuser/.local/bin:$PATH
WORKDIR /home/appuser/app

# Copy application source
COPY --chown=appuser:appgroup app /home/appuser/app/app
COPY --chown=appuser:appgroup main.py /home/appuser/app/main.py

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false \
    # Model & HF cache stored on persistent /data volume
    HF_HOME=/data/.huggingface \
    SENTENCE_TRANSFORMERS_HOME=/data/.huggingface \
    # SQLite & ChromaDB on persistent /data volume
    DATABASE_URL=sqlite+aiosqlite:////data/skripsi.db \
    CHROMA_DB_PATH=/data/chroma_db \
    # Allow online model download at runtime
    HF_HUB_OFFLINE=0 \
    TRANSFORMERS_OFFLINE=0 \
    PORT=7860 \
    UVICORN_WORKERS=1

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=15s --start-period=120s --retries=5 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f\"http://localhost:{os.getenv('PORT', '7860')}/health\")"

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860} --workers ${UVICORN_WORKERS:-1} --loop uvloop --http httptools"]
