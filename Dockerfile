# ── Build stage: install dependencies ──────────────────────────────────
FROM python:3.14-slim AS builder

WORKDIR /build

# System deps for scipy/numpy/highspy compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────
FROM python:3.14-slim

# Non-root user for security
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

# OCR stack: tesseract + Polish & English language packs, poppler for pdf2image.
# Installed in runtime stage (not builder) so they end up in the final image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng \
    poppler-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/
COPY start.sh .version ./
RUN chmod +x /app/start.sh

# Create data directory for SQLite (owned by app user)
RUN mkdir -p /app/data && chown -R app:app /app

USER app

# Railway injects PORT at runtime; 8080 is the fallback (Railway's expected default).
ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen(f'http://localhost:{__import__(\"os\").environ.get(\"PORT\",8080)}/health')" || exit 1

CMD ["/app/start.sh"]
