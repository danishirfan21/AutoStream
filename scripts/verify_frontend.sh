#!/usr/bin/env bash
set -euo pipefail
cleanup() { docker compose down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT
command -v docker >/dev/null || { echo "Docker is required for frontend verification."; exit 1; }
command -v npm >/dev/null || { echo "npm is required for frontend verification."; exit 1; }
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
pushd frontend >/dev/null
npm ci
npm run build
npm test -- --run
popd >/dev/null
docker compose build frontend
docker compose up -d db api frontend
for _ in $(seq 1 45); do curl -fsS http://localhost:8000/health >/dev/null && break; sleep 2; done
curl -fsS http://localhost:8000/health >/dev/null
for _ in $(seq 1 30); do curl -fsS http://localhost:5173/ >/dev/null && break; sleep 2; done
curl -fsS http://localhost:5173/ | grep -q '<div id="root"></div>'
cat <<'RESULT'
AUTOSTREAM FRONTEND VERIFY SUCCEEDED:
dependencies
typescript
build
tests
docker
dashboard
RESULT
