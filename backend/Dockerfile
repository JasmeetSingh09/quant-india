FROM python:3.12-slim

# System deps required by some Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────
# Install CPU-only PyTorch first (~200 MB vs ~2 GB for the CUDA build).
# Must run before `pip install -r requirements.txt` so the requirements step
# sees torch as already satisfied and skips it.
RUN pip install --no-cache-dir torch \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Pre-download FinBERT at build time ────────────────────────────────────
# Bakes the ~500 MB model into the image so the first real request is instant.
RUN python -c "\
from transformers import pipeline; \
pipeline('text-classification', model='ProsusAI/finbert', top_k=None)"

# ── Application code ──────────────────────────────────────────────────────
COPY . .

# Render sets $PORT; default to 8000 for local runs
ENV PORT=8000

# Persistent data lives at /app/data when a Render disk is mounted
# (watchlist.json, portfolio.json, simulations DB, screener cache).
# Modules use relative paths from /app, so create the dir unconditionally.
RUN mkdir -p /app/data

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# 2 workers: enough for a 2-core Render Standard instance.
# --timeout 120 lets slow endpoints (FinBERT, backtest) finish without 502s.
CMD ["sh", "-c", \
    "uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 2 --timeout-keep-alive 120"]
