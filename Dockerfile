# ── Build stage: install dependencies ──────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for scipy/numpy/highspy compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────
FROM python:3.11-slim

# Non-root user for security
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/
COPY start.sh ./
RUN chmod +x /app/start.sh

# Create data directory for SQLite (owned by app user)
RUN mkdir -p /app/data && chown -R app:app /app

USER app

# Railway injects PORT; default to 8000
ENV PORT=8000
EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen(f'http://localhost:{__import__(\"os\").environ.get(\"PORT\",8000)}/health')" || exit 1

CMD ["/app/start.sh"]
