FROM python:3.11-slim AS builder

WORKDIR /build

ARG MODEL_NAME=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install \
       torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

ENV PYTHONPATH=/install/lib/python3.11/site-packages
ENV PATH="/install/bin:${PATH}"

WORKDIR /assets

RUN python - <<'PY'
from sentence_transformers import SentenceTransformer
from optimum.onnxruntime import ORTModelForFeatureExtraction
from transformers import AutoTokenizer
import os

model_id = os.environ.get("MODEL_NAME", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

SentenceTransformer(model_id).save("/assets/model")
ort_model = ORTModelForFeatureExtraction.from_pretrained(model_id, export=True)
tokenizer = AutoTokenizer.from_pretrained(model_id)
ort_model.save_pretrained("/assets/models_onnx")
tokenizer.save_pretrained("/assets/models_onnx")
PY


FROM python:3.11-slim AS runtime

RUN groupadd --gid 1000 appgroup \
    && useradd --create-home --uid 1000 --gid appgroup appuser

COPY --from=builder /install /usr/local

RUN mkdir -p /data /data/.huggingface /home/appuser/app \
    && chown -R appuser:appgroup /data /home/appuser/app

USER appuser
ENV HOME=/home/appuser \
    PATH=/home/appuser/.local/bin:$PATH
WORKDIR /home/appuser/app

COPY --chown=appuser:appgroup app /home/appuser/app/app
COPY --chown=appuser:appgroup main.py /home/appuser/app/main.py
COPY --from=builder --chown=appuser:appgroup /assets/model /home/appuser/app/model
COPY --from=builder --chown=appuser:appgroup /assets/models_onnx /home/appuser/app/models_onnx

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false \
    HF_HOME=/data/.huggingface \
    DATABASE_URL=sqlite+aiosqlite:////data/skripsi.db \
    CHROMA_DB_PATH=/data/chroma_db \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PORT=7860 \
    UVICORN_WORKERS=1

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f\"http://localhost:{os.getenv('PORT', '7860')}/health\")"

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860} --workers ${UVICORN_WORKERS:-1} --loop uvloop --http httptools"]
