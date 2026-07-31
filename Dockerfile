# =========================
# Builder
# =========================
FROM python:3.11-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY app ./app

RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

# =========================
# Runtime
# =========================
FROM python:3.11-slim

LABEL org.opencontainers.image.title="Python JSON API Server"
LABEL org.opencontainers.image.description="JSONPlaceholder-compatible REST API — FastAPI + SQLAlchemy + Redis"
LABEL org.opencontainers.image.source="https://github.com/dangkhoa2016/Python-JSON-API-Server"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Install from pre-built wheel then discard wheel files
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Create non-root user
RUN groupadd -r app && useradd --no-log-init -r -g app app

# Copy application source
COPY --chown=app:app . .

# Prepare runtime directories
RUN mkdir -p /app/storage \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R app:app /app/storage

USER app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    DB_PATH=/app/storage/data.db

EXPOSE 3000

VOLUME ["/app/storage"]

ENTRYPOINT ["/app/docker-entrypoint.sh"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
