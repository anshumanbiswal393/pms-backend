#!/bin/sh
set -e

echo "Waiting for database..."
python <<'PYEOF'
import os
import sys
import time
import environ

env = environ.Env()
db_url = env('DATABASE_URL', default='')
if db_url:
    import psycopg2
    from urllib.parse import urlparse
    parsed = urlparse(db_url)
    for i in range(30):
        try:
            conn = psycopg2.connect(
                dbname=parsed.path.lstrip('/'),
                user=parsed.username,
                password=parsed.password,
                host=parsed.hostname,
                port=parsed.port or 5432,
            )
            conn.close()
            print("Database is ready.")
            sys.exit(0)
        except psycopg2.OperationalError:
            print("Database not ready, retrying...")
            time.sleep(2)
    print("Database did not become ready in time.")
    sys.exit(1)
PYEOF

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting gunicorn..."
exec gunicorn retrod_pms.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --access-logfile - \
    --error-logfile -
