# ── Stage 1: Build ────────────────────────────────────────────────────────────
# Install all Python dependencies that require native compilation.
FROM python:3.10-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only dependency declarations first — this layer is cached until
# pyproject.toml or setup.py changes, even when app code is modified.
COPY pyproject.toml setup.py ./
# pyproject.toml declares packages in src/ — create empty dir so setuptools resolves deps
RUN mkdir -p src

RUN pip install --no-cache-dir --prefix=/deps ".[ext]" \
    && pip install --no-cache-dir --prefix=/deps \
       asyncpg psycopg2-binary httpx


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
# Lean image: only Python runtime + installed packages, no build toolchain.
FROM python:3.10-slim AS runtime

COPY --from=builder /deps /usr/local

WORKDIR /app

# Copy application source code
COPY . .

# Pre-create directories that may be mounted as volumes;
# if a volume is mounted here at runtime these dirs are replaced by the mount.
RUN mkdir -p logs data/groups user_profiles

EXPOSE 8001

# SIGTERM → gunicorn master → graceful worker shutdown
STOPSIGNAL SIGTERM

CMD ["gunicorn", "-c", "gunicorn_config.py", "app:app"]
