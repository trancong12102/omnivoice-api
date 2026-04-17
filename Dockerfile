# syntax=docker/dockerfile:1.7

# Base: CUDA 12.8 runtime (matches pixi prod feature extra-index cu128)
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PIXI_HOME=/usr/local \
    PIXI_CACHE_DIR=/opt/pixi-cache \
    PATH=/usr/local/bin:/root/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/root/.cache/huggingface

# System deps: pixi needs curl + ca-certs; audio stack needs ffmpeg + libsndfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates git ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install pixi
RUN curl -fsSL https://pixi.sh/install.sh | bash \
    && pixi --version

WORKDIR /app

# Copy manifest + source together — editable install needs src/ present.
# Build context should exclude .pixi/, .venv/, tests, etc. (see .dockerignore)
COPY pixi.toml pixi.lock pyproject.toml ./
COPY src ./src

# Resolve prod env. Buildkit cache mount keeps pypi/conda downloads across builds.
RUN --mount=type=cache,target=/opt/pixi-cache \
    pixi install -e prod --locked

EXPOSE 8000

# Healthcheck hits /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["pixi", "run", "-e", "prod", "serve-prod"]
