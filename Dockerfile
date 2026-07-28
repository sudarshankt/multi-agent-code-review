# ── Stage 1: Build React frontend ──
FROM node:20-alpine AS frontend-build

WORKDIR /build
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci

COPY dashboard/ ./

# Baked into the built JS bundle at build time (visible to anyone who opens
# devtools — same trade-off as any shared secret in a client-side app).
# Leave unset for a build with no dashboard-side auth (mutating actions
# will 401 unless called directly, e.g. via curl, with the header).
ARG VITE_API_KEY=
ENV VITE_API_KEY=$VITE_API_KEY
RUN npm run build


# ── Stage 2: Combined backend + serve ──
FROM python:3.12-slim

WORKDIR /app

# System deps: nginx (serve static + reverse proxy), supervisor (process mgr), curl (healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python deps + package install (README.md needed by hatchling metadata)
# Install CPU-only PyTorch first to avoid pulling ~2 GB of CUDA libraries
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir .

# Remaining backend assets
COPY scripts/ scripts/
COPY knowledge_base/ knowledge_base/

# Deploy configs (nginx + supervisor)
COPY deploy/ deploy/

# Eval (finding_eval's security golden samples live under tests_local/test_data/,
# not eval/ — without this, the eval matrix's security run 500s on a
# FileNotFoundError since the manifest points at a path that doesn't exist)
COPY eval/ eval/
COPY tests_local/ tests_local/

# Frontend static build from stage 1
COPY --from=frontend-build /build/dist /app/static

EXPOSE 80

ENV APP_ENV=production

CMD ["supervisord", "-c", "/app/deploy/supervisord.conf"]
