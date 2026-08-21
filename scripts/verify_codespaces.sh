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
if ! docker compose exec -T api test -f /app/fixtures/dealer_feed_v1.csv; then
  echo "Expected fixture is missing from the API image: /app/fixtures/dealer_feed_v1.csv" >&2
  exit 1
fi
if ! docker compose exec -T api test -f /app/fixtures/marketplace_feed.json; then
  echo "Expected fixture is missing from the API image: /app/fixtures/marketplace_feed.json" >&2
  exit 1
fi

assert_json() {
  local expression="$1"
  python3 -c "import json, sys; data=json.load(sys.stdin); assert ${expression}, data"
}
api_json() {
  local expected_status="$1"
  shift
  local response_file status
  response_file="$(mktemp)"
  status="$(curl --silent --show-error --output "$response_file" --write-out '%{http_code}' "$@")"
  if [[ "$status" != "$expected_status" ]]; then
    echo "API request failed: HTTP $status (expected $expected_status)" >&2
    cat "$response_file" >&2
    rm -f "$response_file"
    return 1
  fi
  cat "$response_file"
  rm -f "$response_file"
}
psql_scalar() {
  docker compose exec -T db psql -U "${POSTGRES_USER:-autostream}" -d "${POSTGRES_DB:-autostream}" \
    -v ON_ERROR_STOP=1 -tA -c "$1"
}
assert_scalar() {
  local name="$1"
  local expected="$2"
  local sql="$3"
  local actual
  actual="$(psql_scalar "$sql")"
  actual="${actual//$'\r'/}"
  if [[ "$actual" != "$expected" ]]; then
    echo "ASSERT FAILED: $name" >&2
    echo "expected: $expected" >&2
    echo "actual: $actual" >&2
    return 1
  fi
}

api_json 201 -X POST 'http://localhost:8000/api/v1/ingestion/csv?fixture=dealer_feed_v1.csv' | assert_json "data['status']=='completed' and data['inserted_records']==3 and data['updated_records']==0 and data['duplicate_records']==0 and data['invalid_records']==0"
assert_scalar "vehicle count after v1" "3" "SELECT count(*) FROM vehicles;"
assert_scalar "provenance count after v1" "3" "SELECT count(*) FROM vehicle_source_records;"
assert_scalar "observation count after v1" "3" "SELECT count(*) FROM vehicle_price_observations;"
accord_before="$(psql_scalar "SELECT updated_at FROM vehicles WHERE vin = '1HGCM82633A004352';")"

api_json 201 -X POST 'http://localhost:8000/api/v1/ingestion/csv?fixture=dealer_feed_v1.csv' | assert_json "data['inserted_records']==0 and data['updated_records']==0 and data['duplicate_records']==3"
assert_scalar "vehicle count after replay" "3" "SELECT count(*) FROM vehicles;"
assert_scalar "provenance count after replay" "3" "SELECT count(*) FROM vehicle_source_records;"
assert_scalar "observation count after replay" "3" "SELECT count(*) FROM vehicle_price_observations;"
assert_scalar "Accord updated_at after replay" "$accord_before" "SELECT updated_at FROM vehicles WHERE vin = '1HGCM82633A004352';"

api_json 201 -X POST 'http://localhost:8000/api/v1/ingestion/csv?fixture=dealer_feed_v2.csv' | assert_json "data['inserted_records']==1 and data['updated_records']==2 and data['duplicate_records']==1 and data['invalid_records']==0"
assert_scalar "vehicle count after v2" "4" "SELECT count(*) FROM vehicles;"
assert_scalar "provenance count after v2" "6" "SELECT count(*) FROM vehicle_source_records;"
assert_scalar "observation count after v2" "6" "SELECT count(*) FROM vehicle_price_observations;"
assert_scalar "Tesla canonical trim" "Long Range AWD" "SELECT trim FROM vehicles WHERE vin = '5YJ3E1EA7PF123456';"
assert_scalar "Accord updated_at after price update" "$accord_before" "SELECT updated_at FROM vehicles WHERE vin = '1HGCM82633A004352';"

invalid_run="$(api_json 201 -X POST 'http://localhost:8000/api/v1/ingestion/csv?fixture=invalid_feed.csv')"
printf '%s' "$invalid_run" | assert_json "data['status']=='completed' and data['invalid_records']==2"
invalid_id="$(printf '%s' "$invalid_run" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")"
curl --fail --silent "http://localhost:8000/api/v1/ingestion/runs/${invalid_id}/errors" | assert_json "len(data)==2"
curl --fail --silent 'http://localhost:8000/api/v1/vehicles?make=Honda' | assert_json "len(data)==1 and data[0]['vin']=='1HGCM82633A004352'"

api_json 201 -X POST 'http://localhost:8000/api/v1/ingestion/json?fixture=marketplace_feed.json' | assert_json "data['source_name']=='marketplace_json' and data['inserted_records']==1 and data['updated_records']==2 and data['duplicate_records']==0 and data['invalid_records']==1"
assert_scalar "canonical vehicle count after JSON" "5" "SELECT count(*) FROM vehicles;"
assert_scalar "provenance count after JSON" "9" "SELECT count(*) FROM vehicle_source_records;"
assert_scalar "observation count after JSON" "9" "SELECT count(*) FROM vehicle_price_observations;"
assert_scalar "shared VIN provenance count" "2" "SELECT count(*) FROM vehicle_source_records s JOIN vehicles v ON v.id = s.vehicle_id WHERE v.vin = '1HGCM82633A004352';"
assert_scalar "JSON source record identity" "1" "SELECT count(*) FROM vehicle_source_records WHERE source_name = 'marketplace_json' AND source_record_id = 'mk-1001';"
assert_scalar "cross-source conflict rule" "EX" "SELECT trim FROM vehicles WHERE vin = '1HGCM82633A004352';"
api_json 200 'http://localhost:8000/api/v1/vehicles/1HGCM82633A004352/sources' | assert_json "{item['source_name'] for item in data} == {'dealer_csv', 'marketplace_json'}"
api_json 200 'http://localhost:8000/api/v1/vehicles/1HGCM82633A004352/price-history' | assert_json "{item['source_name'] for item in data} == {'dealer_csv', 'marketplace_json'}"
api_json 201 -X POST 'http://localhost:8000/api/v1/ingestion/json?fixture=marketplace_feed.json' | assert_json "data['inserted_records']==0 and data['updated_records']==0 and data['duplicate_records']==3 and data['invalid_records']==1"
assert_scalar "provenance count after JSON replay" "9" "SELECT count(*) FROM vehicle_source_records;"
assert_scalar "observation count after JSON replay" "9" "SELECT count(*) FROM vehicle_price_observations;"

docker compose exec -T -e RUN_POSTGRES_INTEGRATION=1 -e PYTHONPATH=. api pytest tests -q

verified=true
echo 'AUTOSTREAM MULTISOURCE VERIFY SUCCEEDED:'
echo 'API'
echo 'PostgreSQL'
echo 'migrations'
echo 'CSV ingestion'
echo 'normalization'
echo 'idempotency'
echo 'JSON ingestion'
echo 'VIN deduplication'
echo 'cross-source provenance'
echo 'conflict handling'
echo 'price history'
echo 'error handling'
echo 'persistence'
echo 'tests'
