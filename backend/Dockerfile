# The exact base image production built on 2026-10-06 (cf9e3be), not the moving
# 3.12-slim tag: a rebuild must not change Python or the OS under the code.
FROM python:3.12-slim@sha256:ddb0207ae1f0356c2b724d740769b0c5f5f51cc54a0525178f721825f78fe74c

# System deps required by some Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────
# Locked to the 93 files production installed on 2026-10-06 (owner-approved
# 2026-10-15): every package at an exact version, every file checked against its
# sha256, nothing resolved (--no-deps), so a rebuild installs the same stack and
# a library upgrade can only arrive as a reviewed change to these files.
# CPU-only PyTorch first (~200 MB vs ~2 GB for the CUDA build), from its own index.
# requirements.txt remains the readable list of direct dependencies; it is not
# what the image installs. See docs/audit/production_dependency_manifest_2026-10-06.json.
COPY requirements-production-locked-torch-2026-10-06.txt requirements-production-locked-2026-10-06.txt ./
RUN pip install --no-cache-dir --require-hashes --no-deps \
        --index-url https://download.pytorch.org/whl/cpu \
        -r requirements-production-locked-torch-2026-10-06.txt \
 && pip install --no-cache-dir --require-hashes --no-deps \
        -r requirements-production-locked-2026-10-06.txt \
 && pip check

# ── Pre-download FinBERT at build time ────────────────────────────────────
# Bakes the ~500 MB model into the image so the first real request is instant.
RUN python -c "\
from transformers import pipeline; \
pipeline('text-classification', model='ProsusAI/finbert', revision='4556d13015211d73dccd3fdd39d39232506f3e43', top_k=None)"

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

# SINGLE worker on purpose: each worker loads its OWN ~1.5 GB FinBERT copy, so
# 2 workers (~3 GB) OOM-killed the 2 GB Standard instance. The app is I/O-bound
# (yfinance/news) and FastAPI runs sync endpoints in a threadpool, so one worker
# handles the load fine — and it avoids duplicating the background schedulers.
# --timeout 120 lets slow endpoints (FinBERT, backtest) finish without 502s.
CMD ["sh", "-c", \
    "uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 120"]
