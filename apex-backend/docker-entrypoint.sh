#!/bin/sh
set -e

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
