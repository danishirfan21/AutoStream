#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] || cp .env.example .env
cleanup(){ docker compose down -v --remove-orphans >/dev/null 2>&1 || true; }; trap cleanup EXIT
docker compose up -d --build db api
for _ in $(seq 1 60); do curl -fsS http://localhost:8000/ready >/dev/null && break; sleep 2; done
curl -fsS http://localhost:8000/ready >/dev/null
docker compose exec -T api python scripts/generate_benchmark_data.py --vehicles 10000 --reset
docker compose exec -T db psql -U autostream -d autostream -tAc 'SELECT count(*) FROM vehicles' | grep -qx 10000
docker compose exec -T api python scripts/benchmark_postgres.py --iterations 30 --plans-dir /tmp/autostream-performance | tee /tmp/autostream-performance.json
mkdir -p docs/performance
docker compose cp api:/tmp/autostream-performance/. docs/performance/
echo 'AUTOSTREAM PERFORMANCE VERIFY SUCCEEDED:'; echo 'synthetic data'; echo 'row counts'; echo 'benchmark queries'; echo 'query plans'; echo 'report'
