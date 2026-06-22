# Backend Dockerfile — works on Railway, Render, Fly.io, or any container host.
# FinBERT + PyTorch need ~1.5GB RAM, so pick a host plan with >=2GB.

FROM python:3.12-slim

# System deps some Python wheels need
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download FinBERT at build time so first request isn't slow
RUN python -c "from transformers import pipeline; pipeline('text-classification', model='ProsusAI/finbert', top_k=None)"

# Copy the rest of the backend
COPY . .

# Render/Railway provide $PORT; default to 8000 locally
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
