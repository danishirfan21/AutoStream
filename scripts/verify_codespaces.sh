#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
[[ -f .env ]] || cp .env.example .env

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is unavailable in this Codespace." >&2
  echo "Run 'Codespaces: Rebuild Container' to apply .devcontainer/devcontainer.json, then retry." >&2
  exit 1
fi

verified=false
cleanup() {
  if [[ "$verified" == true ]]; then
    docker compose down -v --remove-orphans
  else
    echo "Verification failed; Compose services were left running for diagnosis." >&2
    docker compose ps >&2 || true
    docker compose logs --no-color >&2 || true
    echo "Clean up with: docker compose down -v --remove-orphans" >&2
  fi
}
trap cleanup EXIT

docker compose down -v --remove-orphans
docker compose up -d --build

for _ in $(seq 1 60); do
  if docker compose exec -T db pg_isready -U autostream -d autostream >/dev/null 2>&1; then break; fi
  sleep 2
done
docker compose exec -T db pg_isready -U autostream -d autostream >/dev/null

for _ in $(seq 1 60); do
  if curl --fail --silent http://localhost:8000/ready >/dev/null; then break; fi
  sleep 2
done
curl --fail --silent http://localhost:8000/health >/dev/null
curl --fail --silent http://localhost:8000/ready >/dev/null
docker compose exec -T api alembic upgrade head

assert_json() {
  local expression="$1"
  python3 -c "import json, sys; data=json.load(sys.stdin); assert ${expression}, data"
}
psql_scalar() {
  docker compose exec -T db psql -U autostream -d autostream -Atqc "$1"
}

curl --fail --silent -X POST 'http://localhost:8000/api/v1/ingestion/csv?fixture=dealer_feed_v1.csv' | assert_json "data['status']=='completed' and data['inserted_records']==3 and data['updated_records']==0 and data['duplicate_records']==0 and data['invalid_records']==0"
[[ "$(psql_scalar 'SELECT count(*) FROM vehicles')" == "3" ]]
[[ "$(psql_scalar 'SELECT count(*) FROM vehicle_source_records')" == "3" ]]
[[ "$(psql_scalar 'SELECT count(*) FROM vehicle_price_observations')" == "3" ]]
accord_before="$(psql_scalar \"SELECT updated_at FROM vehicles WHERE vin = '1HGCM82633A004352'\")"

curl --fail --silent -X POST 'http://localhost:8000/api/v1/ingestion/csv?fixture=dealer_feed_v1.csv' | assert_json "data['inserted_records']==0 and data['updated_records']==0 and data['duplicate_records']==3"
[[ "$(psql_scalar 'SELECT count(*) FROM vehicles')" == "3" ]]
[[ "$(psql_scalar 'SELECT count(*) FROM vehicle_source_records')" == "3" ]]
[[ "$(psql_scalar 'SELECT count(*) FROM vehicle_price_observations')" == "3" ]]
[[ "$(psql_scalar \"SELECT updated_at FROM vehicles WHERE vin = '1HGCM82633A004352'\")" == "$accord_before" ]]

curl --fail --silent -X POST 'http://localhost:8000/api/v1/ingestion/csv?fixture=dealer_feed_v2.csv' | assert_json "data['inserted_records']==1 and data['updated_records']==2 and data['duplicate_records']==1 and data['invalid_records']==0"
[[ "$(psql_scalar 'SELECT count(*) FROM vehicles')" == "4" ]]
[[ "$(psql_scalar 'SELECT count(*) FROM vehicle_source_records')" == "6" ]]
[[ "$(psql_scalar 'SELECT count(*) FROM vehicle_price_observations')" == "6" ]]
[[ "$(psql_scalar \"SELECT trim FROM vehicles WHERE vin = '5YJ3E1EA7PF123456'\")" == "Long Range AWD" ]]
[[ "$(psql_scalar \"SELECT updated_at FROM vehicles WHERE vin = '1HGCM82633A004352'\")" == "$accord_before" ]]

invalid_run="$(curl --fail --silent -X POST 'http://localhost:8000/api/v1/ingestion/csv?fixture=invalid_feed.csv')"
printf '%s' "$invalid_run" | assert_json "data['status']=='completed' and data['invalid_records']==2"
invalid_id="$(printf '%s' "$invalid_run" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")"
curl --fail --silent "http://localhost:8000/api/v1/ingestion/runs/${invalid_id}/errors" | assert_json "len(data)==2"
curl --fail --silent 'http://localhost:8000/api/v1/vehicles?make=Honda' | assert_json "len(data)==1 and data[0]['vin']=='1HGCM82633A004352'"

docker compose exec -T -e RUN_POSTGRES_INTEGRATION=1 -e PYTHONPATH=. api pytest tests -q

verified=true
echo 'AUTOSTREAM BASELINE VERIFY SUCCEEDED:'
echo 'API'
echo 'PostgreSQL'
echo 'migrations'
echo 'CSV ingestion'
echo 'normalization'
echo 'idempotency'
echo 'incremental update'
echo 'provenance'
echo 'error handling'
echo 'persistence'
echo 'tests'
