#!/bin/sh
set -eu

cd /srv

export PYTHONPATH="/srv${PYTHONPATH:+:$PYTHONPATH}"

legacy_revision="$(
python - <<'PY'
import os
import sqlite3

database_url = os.environ.get("DATABASE_URL", "")
prefix = "sqlite:///"
if not database_url.startswith(prefix):
    raise SystemExit(0)

db_path = database_url[len(prefix):]
if not os.path.exists(db_path):
    raise SystemExit(0)

conn = sqlite3.connect(db_path)
try:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    current_revision = None
    if "alembic_version" in tables:
        try:
            row = conn.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
        except sqlite3.OperationalError:
            row = None
        if row and row[0]:
            current_revision = row[0]
finally:
    conn.close()

if current_revision:
    print("")
elif "gc_jobs" in tables:
    print("0003_gc_jobs")
elif "web_sessions" in tables:
    print("0002_web_sessions")
elif "users" in tables:
    print("0001_phase1_schema")
else:
    print("")
PY
)"

if [ -n "$legacy_revision" ]; then
  python -m alembic -c backend/alembic.ini stamp "$legacy_revision"
fi

python -m alembic -c backend/alembic.ini upgrade head

exec python -m uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
