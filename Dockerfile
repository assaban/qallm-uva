# syntax=docker/dockerfile:1.6
#
# QALLM container image. Multi-stage build:
#   1. node-build: compiles the React frontend to static files.
#   2. python-runtime: installs the Python package and copies the static
#      build in. The FastAPI app serves both the API and the static UI
#      from a single port (default 8000).
#
# Build:   docker build -t qallm:latest .
# Run:     docker run --rm -p 8000:8000 --env-file .env qallm:latest
# Compose: see docker-compose.yml.


# -------- Stage 1: build the frontend --------
FROM node:20-alpine AS node-build

WORKDIR /app/frontend

# Copy lockfile and manifest first so the npm install layer caches well.
COPY web/frontend/package.json web/frontend/package-lock.json* ./
RUN npm ci --silent

# Now copy sources and build.
COPY web/frontend/ ./
RUN npm run build


# -------- Stage 2: Python runtime --------
FROM python:3.12-slim AS runtime

# System dependencies:
#   git           ingestion can clone repos
#   build-essential transient: some Python packages compile on install
# We keep the image small by removing apt caches afterwards.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user. The Python sandbox does pytest + coverage in
# subprocesses inside the container; root is unnecessary and a footgun.
RUN useradd --create-home --uid 1000 qallm
WORKDIR /home/qallm/app

# Install Python deps first, leveraging Docker layer cache.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[experiments]"

# Drop build-essential now that pip install is done; it added ~250MB.
RUN apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Copy the built frontend into the location FastAPI will serve from.
# Vite's outDir is configured as ../dist (i.e. web/dist), so the build
# stage's output sits at /app/dist.
COPY --from=node-build /app/dist ./web/dist

# Outputs directory needs to be writable by the qallm user. We create it
# now and chown so a volume mount inherits ownership cleanly.
RUN mkdir -p /home/qallm/app/outputs /home/qallm/app/uploads \
    && chown -R qallm:qallm /home/qallm/app

USER qallm

# Tell the API where the built frontend lives. Without this, the static
# mount tries to resolve from __file__, which points to site-packages
# after a non-editable install.
ENV QALLM_FRONTEND_DIST=/home/qallm/app/web/dist

EXPOSE 8000

# uvicorn workers=1 because the in-memory session and job stores are
# process-local. Multi-worker requires shared state (Redis, etc.) and
# is out of scope for the beta.
CMD ["uvicorn", "qallm.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]