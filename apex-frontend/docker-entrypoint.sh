#!/bin/sh
set -e

export HOSTNAME="${HOSTNAME:-0.0.0.0}"
export PORT="${PORT:-3000}"

echo "Starting Next.js standalone on ${HOSTNAME}:${PORT}..."
exec node server.js
