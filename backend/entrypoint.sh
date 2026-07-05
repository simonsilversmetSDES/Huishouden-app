#!/bin/sh
set -e

mkdir -p /data/db

echo "Database-migraties uitvoeren..."
alembic upgrade head

echo "Seed-data controleren..."
python -m app.seed

echo "Backend starten op :8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
