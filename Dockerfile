# syntax=docker/dockerfile:1.7
# Multi-stage Dockerfile for the Quant Research Platform.
#
# Targets:
#   - dev         → builds with full toolchain, runs as root, mounts source.
#                   Build:  docker build --target dev -t qrp:dev .
#                   Run:    docker run --rm -p 8000:8000 -p 8501:8501 -v $PWD:/app qrp:dev
#   - production  → slim runtime, non-root, gunicorn-style uvicorn workers.
#                   Build:  docker build --target production -t qrp:latest .
#
# Both targets install requirements.txt + qrp_platform/dashboard/requirements.txt.

ARG PYTHON_VERSION=3.11-slim-bookworm

# ---------------------------------------------------------------------------
# Base: shared system deps + Python toolchain
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# System libs needed for scientific stack (numpy/pandas/sklearn wheels are
# usually manylinux, but a slim base is enough).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Dependencies layer (cached independently of source)
# ---------------------------------------------------------------------------
FROM base AS deps

COPY requirements.txt qrp_platform/dashboard/requirements.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt -r qrp_platform/dashboard/requirements.txt

# ---------------------------------------------------------------------------
# Dev target: hot code via volume mount, both services runnable
# ---------------------------------------------------------------------------
FROM deps AS dev

COPY . .

EXPOSE 8000 8501
CMD ["bash", "-lc", "uvicorn qrp_platform.api.main:app --host 0.0.0.0 --port 8000 --reload & streamlit run qrp_platform/dashboard/app.py --server.port 8501 --server.address 0.0.0.0"]

# ---------------------------------------------------------------------------
# Production target: non-root, uvicorn workers, dashboard sidecar
# ---------------------------------------------------------------------------
FROM deps AS production

# Non-root user
RUN useradd --create-home --shell /bin/bash qrp \
 && mkdir -p /app/data /app/results \
 && chown -R qrp:qrp /app
USER qrp

COPY --chown=qrp:qrp . .

ENV DATA_DIR=/app/data \
    RESULTS_DIR=/app/results \
    API_HOST=0.0.0.0 \
    API_PORT=8000

EXPOSE 8000 8501

# Default: launch API in the foreground. The dashboard is its own service in
# docker-compose so this container stays focused on the API.
CMD ["uvicorn", "qrp_platform.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]