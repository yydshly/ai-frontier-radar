# AI Frontier Radar — Linux container image.
#
# Bundles the system deps the app needs at runtime: ffmpeg (audio/video) and a
# CJK font (fonts-noto-cjk, for the Chinese report images / video). Node.js is
# NOT installed here — the Remotion video path is optional; the PIL video path
# and everything else work without it.
#
# Build:  docker build -t aifrontier-radar .
# Run:    docker run -p 8765:8765 --env-file .env -v "$PWD/data:/app/data" \
#                 -v "$PWD/runtime:/app/runtime" aifrontier-radar
FROM python:3.10-slim

# Runtime system dependencies.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-noto-cjk \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8765

WORKDIR /app

# Install Python deps first (layer cache: only re-runs when requirements change).
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Application code + assets.
COPY app ./app
COPY scripts ./scripts
COPY config ./config
COPY assets ./assets

# data/ and runtime/ are mounted as volumes at run time (persisted on the host);
# create empty mount points + the logs dir so the app can write immediately.
RUN mkdir -p data runtime logs

# Run as a non-root user.
RUN useradd --create-home --uid 10001 radar \
    && chown -R radar:radar /app
USER radar

EXPOSE 8765

# The web service. The daily cycle is run separately (see docs/LINUX_DEPLOYMENT.md):
#   docker compose run --rm radar python scripts/run_daily_cycle.py --apply
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
