# ── PubSub Server — Multi-stage Dockerfile ──────────────────────────────────
# Stage 1: Install dependencies (cached layer)
# Stage 2: Production image (slim, no build tools)
#
# Ports:
#   10001 — TCP broker (custom binary protocol, devices connect here)
#   8080 — Query API (FastAPI, dashboard/backend reads telemetry)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Builder ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install only runtime Python deps (no gcc/librdkafka — aiokafka is pure Python)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Production ────────────────────────────────────────────────────
FROM python:3.12-slim

# Security: run as non-root
RUN groupadd -r iot && useradd -r -g iot -d /app -s /sbin/nologin iot

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code (respects .dockerignore)
COPY . .

# Own files by the app user
RUN chown -R iot:iot /app

USER iot

# Expose ports: 10001 (TCP broker), 8080 (Query API)
EXPOSE 10001 8080

# Health check — Query API endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "main.py"]
