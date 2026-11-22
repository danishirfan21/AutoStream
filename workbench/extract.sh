#!/usr/bin/env bash
# Read-only extraction of AutoStream evidence to CSV. Usage: WORKBENCH_DATABASE_URL=... extract.sh OUT_DIR
# Needs only psql. Every query runs with default_transaction_read_only=on and UTC time.
# There is deliberately NO default database: the caller must name one.
# The pipe through tr deletes the CR that psql adds on Windows, so output is byte-identical everywhere
# (payloads containing a literal carriage return would lose it; none exist in the fixtures).
set -euo pipefail
: "${WORKBENCH_DATABASE_URL:?set WORKBENCH_DATABASE_URL to a libpq URI, e.g. postgresql://user@host:5432/dbname}"
out="${1:?usage: extract.sh OUT_DIR}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
psql_bin="${PSQL:-psql}"
export PGOPTIONS="-c default_transaction_read_only=on -c TimeZone=UTC -c statement_timeout=60000"
mkdir -p "$out"
for f in "$here"/sql/*.sql; do
  name="$(basename "$f" .sql)"; name="${name#[0-9][0-9]_}"
  query="$(sed -e 's/[[:space:]]*;[[:space:]]*$//' "$f")"
  tmp="$out/.$name.csv.tmp"
  "$psql_bin" -X -q -v ON_ERROR_STOP=1 -d "$WORKBENCH_DATABASE_URL" \
    -c "COPY ($query) TO STDOUT WITH (FORMAT csv, HEADER true)" | tr -d '\r' > "$tmp"
  mv "$tmp" "$out/$name.csv"
  echo "wrote $out/$name.csv" >&2
done
