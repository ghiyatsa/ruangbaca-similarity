# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: builder
# Install dependencies dan export model ke format ONNX untuk performa CPU maksimal.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps minimal untuk build C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# 1. Install PyTorch CPU-only (Menghemat ~4GB+ dibanding versi default/CUDA)
# 2. Install dependencies lainnya
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install \
       torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# Pastikan Python builder bisa menemukan package yang diinstall di /install
ENV PYTHONPATH=/install/lib/python3.11/site-packages
ENV PATH="/install/bin:${PATH}"

# Export Model ke ONNX saat build (Maximizing CPU Performance)
# Model akan disimpan di /models_onnx agar aplikasi bisa load secara offline
ARG MODEL_NAME=paraphrase-multilingual-MiniLM-L12-v2
RUN python -m optimum.exporters.onnx \
    --model ${MODEL_NAME} \
    --task feature-extraction \
    /models_onnx

# Juga simpan model asli sebagai fallback (opsional, tapi disarankan)
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
model = SentenceTransformer('${MODEL_NAME}'); \
model.save('/model')"


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: runtime — image production yang bersih dan minimal
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Non-root user untuk keamanan
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --no-create-home appuser

# Copy packages Python dari builder (termasuk torch-cpu)
COPY --from=builder /install /usr/local

# Copy model ONNX dan model fallback
COPY --from=builder /models_onnx /app/models_onnx
COPY --from=builder /model /app/model

# Copy source code (mengikuti .dockerignore agar tidak copy file sampah/db lokal)
COPY --chown=appuser:appgroup . .

# Buat direktori data persistent (Volume harus di-mount ke /data)
RUN mkdir -p /data && chown -R appuser:appgroup /data

# Environment settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Optimasi ONNX Runtime untuk CPU
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    # Path data & model
    DATABASE_URL=sqlite+aiosqlite:////data/skripsi.db \
    CHROMA_DB_PATH=/data/chroma_db \
    # Paksa mode offline (jangan download apapun saat startup)
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

USER appuser

EXPOSE 8181

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8181/health')"

# Jalankan uvicorn dengan optimasi
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8181", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--http", "httptools"]
