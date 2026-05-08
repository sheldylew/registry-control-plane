#!/bin/sh
set -eu

if [ ! -x "./.venv/bin/uvicorn" ]; then
  echo "Missing ./.venv/bin/uvicorn. Create .venv and install backend dependencies first:" >&2
  echo "python3 -m venv .venv && ./.venv/bin/pip install -r backend/requirements.txt" >&2
  exit 1
fi

export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
if [ "${ALLOW_DEV_DEFAULT_CREDENTIALS:-0}" = "1" ]; then
  export ADMIN_PASSWORD="${ADMIN_PASSWORD:-change-me-now}"
  export ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
else
  : "${ADMIN_PASSWORD:?Set ADMIN_PASSWORD or ALLOW_DEV_DEFAULT_CREDENTIALS=1 for local defaults.}"
  : "${ADMIN_EMAIL:?Set ADMIN_EMAIL or ALLOW_DEV_DEFAULT_CREDENTIALS=1 for local defaults.}"
fi
export APP_ENV="${APP_ENV:-development}"

exec ./.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
