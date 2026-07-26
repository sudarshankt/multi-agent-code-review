# ── Stage 1: Build React frontend ──
FROM node:20-alpine AS frontend-build

WORKDIR /build
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci

COPY dashboard/ ./
RUN npm run build


# ── Stage 2: Combined backend + serve ──
FROM python:3.12-slim

WORKDIR /app

# System deps: nginx (serve static + reverse proxy), supervisor (process mgr), curl (healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps + package install (README.md needed by hatchling metadata)
# Install CPU-only PyTorch first to avoid pulling ~2 GB of CUDA libraries
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir ".[rag]"

# Remaining backend assets
COPY scripts/ scripts/
COPY knowledge_base/ knowledge_base/
COPY all-MiniLM-L6-v2-main/ all-MiniLM-L6-v2-main/

# Deploy configs (nginx + supervisor)
COPY deploy/ deploy/

# Frontend static build from stage 1
COPY --from=frontend-build /build/dist /app/static

EXPOSE 80

ENV APP_ENV=production

CMD ["supervisord", "-c", "/app/deploy/supervisord.conf"]
