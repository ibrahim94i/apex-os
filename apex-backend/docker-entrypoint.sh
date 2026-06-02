#!/bin/sh
set -e

echo "Starting embedded Redis..."
mkdir -p /tmp/redis-data
redis-server --daemonize yes \
  --bind 127.0.0.1 \
  --port 6379 \
  --dir /tmp/redis-data \
  --save "" \
  --appendonly no \
  --loglevel warning
sleep 1
if ! redis-cli ping >/dev/null 2>&1; then
  echo "ERROR: embedded Redis failed to start"
  exit 1
fi
export REDIS_URL="redis://127.0.0.1:6379/0"
export CELERY_BROKER_URL="redis://127.0.0.1:6379/1"
export CELERY_RESULT_BACKEND="redis://127.0.0.1:6379/2"

echo "Running database migrations..."
for attempt in 1 2 3 4 5; do
  if alembic upgrade head; then
    echo "Migrations complete."
    break
  fi
  if [ "$attempt" -eq 5 ]; then
    echo "ERROR: migrations failed after 5 attempts — check DATABASE_URL"
    exit 1
  fi
  echo "Migration attempt $attempt failed, retrying in 5s..."
  sleep 5
done

PORT="${PORT:-8000}"
echo "Starting APEX backend on port ${PORT}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
