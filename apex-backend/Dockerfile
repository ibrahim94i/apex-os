# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-prod.txt


FROM python:3.11-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    redis-server \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash apex

COPY --from=builder /install /usr/local
COPY . .

RUN chmod +x /app/docker-entrypoint.sh \
    && chown -R apex:apex /app

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production

USER apex

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/api/v1/health/live" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
