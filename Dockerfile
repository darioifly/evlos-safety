# syntax=docker/dockerfile:1.6
#
# evlos-safety — single-container build (CUDA 12.1, GPU mandatory).
#
# Best practice: multi-stage build.
#   Stage 1 (frontend-builder)  builds the React SPA on a small node image.
#   Stage 2 (runtime)           is the production image: CUDA runtime libs +
#                               Python deps + backend code + built SPA.
# Rationale: the final image never contains node_modules or build tooling,
# and the heavy CUDA/torch layers can be cached independently of the
# frontend churn.

# =============================================================================
# Stage 1 — Build the frontend (React + Vite)
# =============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# Best practice: copy lockfile + package.json first so npm ci's layer is
# cached as long as deps don't change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# =============================================================================
# Stage 2 — Runtime (CUDA 12.1 runtime + Python 3.10 + backend + dist/)
# =============================================================================
# Best practice: use the CUDA *runtime* image (not -base, not -devel) — it
# ships the CUDA shared libs torch needs at inference time without dragging
# in the full toolkit. Tag matches torch 2.5.1+cu121 wheels.
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Ultralytics writes its config under $HOME by default; pin so it lands
    # somewhere predictable on a volume if the operator later mounts it.
    YOLO_CONFIG_DIR=/app/backend/.ultralytics

# OS deps:
#   python3.10 / pip      — runtime
#   libgl1, libglib2.0-0  — opencv-python-headless still dlopens libGL.so.1
#   ca-certificates       — HTTPS to evlos.ifly.it, pytorch index, etc.
#   curl                  — used by HEALTHCHECK
# Best practice: keep apt layer minimal; purge lists at the end.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 \
        python3-pip \
        libgl1 \
        libglib2.0-0 \
        ca-certificates \
        curl \
    && ln -sf /usr/bin/python3.10 /usr/local/bin/python \
    && ln -sf /usr/bin/python3.10 /usr/local/bin/python3 \
    && rm -rf /var/lib/apt/lists/*

# Best practice: install torch + torchvision from the cu121 wheel index FIRST,
# in their own layer, so subsequent rebuilds (when only backend code changes)
# don't redownload ~2.5 GB of GPU wheels.
RUN python -m pip install --upgrade pip \
 && python -m pip install \
        --index-url https://download.pytorch.org/whl/cu121 \
        torch==2.5.1 \
        torchvision==0.20.1

# Then install the rest of the backend Python deps. Copy ONLY requirements.txt
# first to maximize layer caching.
COPY backend/requirements.txt /tmp/requirements.txt
# requirements.txt also lists torch/torchvision but they're already satisfied
# from the cu121 install above — pip is a no-op on those.
RUN python -m pip install -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

# Smoke-test that the GPU/CV libs at least import (build-time check; this
# verifies the apt+pip layers landed coherently — it does NOT exercise CUDA,
# which needs --gpus at run-time).
RUN python -c "import cv2, ultralytics, torch; print('build-time deps OK:', torch.__version__, ultralytics.__version__, cv2.__version__)"

# Copy backend source. The .dockerignore excludes runtime artefacts
# (DB, data/, logs/, .env, weights), so only code + config defaults land here.
COPY backend/ /app/backend/

# Bring in the built SPA from stage 1. main_sqlite.py resolves
# Path(__file__).parent.parent / "frontend" / "dist", i.e. /app/frontend/dist.
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

# WORKDIR matters: main_sqlite.py reads several settings as paths relative
# to CWD (LOG_DIR="logs", ALERT_SCREENSHOT_DIR="data/alert_screenshots",
# Ultralytics' fallback download dir). Anchoring CWD at /app/backend matches
# the absolute paths the other modules compute via Path(__file__).parent[…],
# so screenshots/logs/db all land under the same /app/backend tree the
# compose volumes bind-mount.
WORKDIR /app/backend

EXPOSE 7002

# Healthcheck hits /health — defined inline in main_sqlite.py and returns
# {"status":"ok","mode":"sqlite"}. start-period gives YOLO+restoreState time
# to come up on a cold start before the first probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS http://localhost:7002/health || exit 1

# main_sqlite.py runs uvicorn programmatically under __main__; we just
# invoke it the same way start_fastapi.bat does.
CMD ["python", "main_sqlite.py"]
