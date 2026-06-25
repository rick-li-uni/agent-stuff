#!/bin/bash
set -e

echo "=== 1. Start Postgres ==="
docker compose up -d postgres
echo "Waiting for Postgres..."
sleep 3

echo "=== 2. Install Python deps ==="
pip install -q psycopg[binary] pyyaml google-adk

echo "=== 3. Seed database ==="
cd "$(dirname "$0")"
DATABASE_URL="postgresql://skills:skills@localhost:5432/skills" \
    python -m db.seed

echo "=== Done. Run the agent with: ==="
echo "  DATABASE_URL='postgresql://skills:skills@localhost:5432/skills' adk web --port 8000"
echo "  or: DATABASE_URL='postgresql://skills:skills@localhost:5432/skills' adk run adk-poc"
