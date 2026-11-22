# Step 2: read-only extracts and reproducible sample (DRAFT, for review)

Everything here lives in `workbench/`. No AutoStream application file, schema, API, frontend or fixture was changed. `counts_as_actionable` means "warrants investigation", not "a data defect is confirmed". Mileage regression and attribute drift are anomaly rules, not proof of corruption.

## Files

| Path | Purpose |
|---|---|
| `sql/01..05_*.sql` | The five read-only queries (SELECT only; checked statically by the validator). |
| `extract.sh` | Runs each query through `psql` with `default_transaction_read_only=on`, UTC time, and writes `OUT_DIR/<name>.csv`. Needs only `psql`. There is **no default database**; set `WORKBENCH_DATABASE_URL`. |
| `tools/generate_sample.py` | Rebuilds `sample/` by running the canonical six-step ingestion in a **disposable** database it creates and drops. Uses only dependencies already in `backend/requirements.txt`. |
| `tools/validate_sample.py` | Stdlib-only checks (counts, columns, hashes, provenance, golden traceability, determinism). |
| `sample/*.csv`, `sample/SHA256SUMS` | The generated, committed-in-spirit sample (not committed yet). |
| `.gitattributes` | Forces LF so checksums are stable across platforms. |

## Extracts and columns

| CSV | Rows in sample | Columns | Notes |
|---|---|---|---|
| `vehicles` | 5 | vin, year, make, model, trim | Canonical context only. |
| `source_records` | 9 | vin, source_name, source_record_id, source_timestamp_utc, payload_hash, raw_payload_json | One row per accepted record. Raw evidence kept verbatim (jsonb text). `source_timestamp_utc` is the source-provided time; empty would mean none. |
| `price_observations` | 9 | vin, source_name, observed_at_utc, price, mileage, location, matching_source_records | No `source_record_id` exists in the schema, so link to a source record by (vin, source_name, observed_at_utc = source_timestamp_utc). `matching_source_records` is 1 when unambiguous, 0 when `observed_at` was the ingestion-time fallback, more than 1 when ambiguous. |
| `ingestion_runs` | 6 | run_seq, source_name, status, total/inserted/updated/duplicate/invalid/failed counts, error_message | `run_seq` = start order. |
| `ingestion_errors` | 4 | run_seq, run_source_name, occurrence_in_run, stored_source_record_id, error_type, error_message, raw_payload_json | **One row per rejection occurrence**; distinct records are derived from payloads, so 3 distinct and 4 occurrences are both recoverable. `stored_source_record_id` is as stored (`row-4` for the marketplace reject). |
| `ingestion_steps` | 6 | step, fixture_file, fixture_sha256, note | Written by the generator, not the database: the schema does not record which fixture a run read. Step N = `run_seq` N. |

Deliberately excluded: database UUIDs, `ingested_at`, run start/end times (non-reproducible, and never valid ordering keys). Ordering in every query is by content, so output is deterministic.

## How exports map to the approved golden findings

Finding IDs are built from feed-supplied values and rule IDs (see `EXPECTED_FINDINGS_NOTES.md`); these are the rows each golden row cites. `validate_sample.py` performs each lookup.

| Golden finding | Evidence rows |
|---|---|
| MILEAGE_REGRESSION (Honda, F-150) | `price_observations`: later row (marketplace) and previous row (dealer) by vin, source, `observed_at_utc` = golden `timestamp_a/b`; `mileage` equals `value_a/b`. Matching `source_records` row gives `source_record_id` and raw payload. |
| ATTR_CONFLICT (Honda trim) | `source_records`: latest dealer row (2026-02-10) and marketplace `mk-1001`; payload `trim` = EX versus `variant` = EX-L. |
| ATTR_DRIFT (Tesla trim) | `source_records`: the two dealer rows for the VIN (2026-01-10 and 2026-02-10); payload `trim` values. |
| REJECTED_RECORD (3) | `ingestion_errors`: rows by `run_source_name` + `stored_source_record_id`; `error_type` = golden evidence column; payload timestamp = golden `timestamp_a`; row count = `occurrences_canonical_sequence`; all rows of one finding share one payload. Rule IDs (`VIN_FORMAT`, `PRICE_NUMERIC`) are step 3 classification and are not computed in SQL. |
| COVERAGE_GAP (3) | `source_records`: VIN present for `source_a`, absent for `source_b`; for the explained gap, a matching `ingestion_errors` row exists for the missing source. |
| 4 rejection occurrences | `ingestion_errors` equals `EXPECTED_REJECTION_OCCURRENCES.csv` on (step = `run_seq`, record id, error type). |

## Running it

Disposable server (example; any local throwaway PostgreSQL works, do not use the Compose or verifier database):

```
python workbench/tools/generate_sample.py --admin-url postgresql://USER@127.0.0.1:PORT/postgres [--psql PATH] [--out DIR]
python workbench/tools/validate_sample.py [--sample DIR] [--compare OTHER_DIR]
```

Extracting from a real database later (read-only):

```
WORKBENCH_DATABASE_URL=postgresql://user@host:5432/db workbench/extract.sh OUT_DIR
```

The generator refuses non-local servers, creates `workbench_sample_<random>`, migrates and ingests only inside it, proves the extraction path cannot write, and drops the database in a `finally` block.

## Known limitations (documented, not defects)

1. Observations have no `source_record_id`; the link above relies on timestamp equality. Two records of one source and VIN with the same timestamp would show `matching_source_records` > 1 (not present in the fixtures).
2. A payload with no price creates no observation, so mileage evidence for it exists only in `raw_payload_json`.
3. `error_message` is library text (Pydantic includes a version-dependent URL). It is evidence only and is not used for classification or IDs.
4. `run_seq` is the order within one database. In a long-lived database it is not the same as the golden step number; the manifest only describes the generated sample.
5. `extract.sh` strips carriage returns from output; a payload containing a literal CR would be altered (none in the fixtures).
6. The error-row ordering within a run is content-based, so two identical rejected payloads in one run would be indistinguishable apart from `occurrence_in_run`.

## Deviations from the golden specification

None. The golden CSVs and notes were not modified; the extracts reproduce every cited value, timestamp, record ID, error type and occurrence count.

## Step 4: opt-in PostgreSQL extraction integration test

`tests/test_pg_extraction_integration.py` (29 tests, marker `pg_integration`) is skipped unless `WORKBENCH_PG_INTEGRATION=1`. It starts a **temporary cluster** (`tests/pg_harness.py`: own `initdb` data directory under the OS temp dir, `127.0.0.1`, free port, trust auth), creates a random `workbench_it_<hex>` database, migrates it with Alembic, runs the six canonical ingestion steps, runs `extract.sh`, and checks:

- 5 vehicles, 9 source records, 9 observations, 6 runs, 4 rejection occurrences (3 distinct payloads), in the database and in the CSVs.
- Extracts equal the committed sample (parsed rows, `error_message` excluded as library text; the three files without volatile columns are byte-identical). Database UUIDs and `ingested_at` are never extracted.
- `validate_sample.py` passes on the fresh extract, and the detector reproduces the 10 golden findings in `--synthetic-fixtures` mode (default real-data mode finds the same 10, 9 actionable).
- Read-only: table fingerprints (row count and md5 of every row) are identical before and after extraction; INSERT/UPDATE/DELETE/TRUNCATE/DROP/CREATE are rejected with SQLSTATE `25006` (a code, not message text); an unmodified copy of `extract.sh` given a hostile `DELETE ... RETURNING` query fails and changes nothing; a control in a separate scratch database shows writes do succeed without the option.
- Teardown (`finally` + `atexit`) stops the server and deletes the directory, including after a simulated failed check and after a failed start.

```
$env:WORKBENCH_PG_INTEGRATION = "1"; $env:WORKBENCH_PG_BIN = "<postgres-bin-dir>"   # dir containing initdb, pg_ctl, psql
python -m pytest workbench -m pg_integration
```

Limitations: needs local PostgreSQL binaries and bash; `default_transaction_read_only` is a session default, not a privilege boundary (a SQL file could in principle switch it off), so the SQL files are additionally checked statically by `validate_sample.py`; on Windows pass `--psql` to the generator with forward slashes.

The detector now defaults to **real-data** classification; the synthetic-fixture classifications require `--synthetic-fixtures` (`golden_compare.py` requests it explicitly).

## Step 5: Power Query scripts and workbook documentation

`queries/` holds 20 Power Query M scripts that read the committed CSV sample (no database). Documentation: `queries/README.md` (architecture), `WORKBOOK_GUIDE.md` (build steps), `INVESTIGATION_LOG.md` (refresh-safe log), `VERIFICATION_CHECKLIST.md` (golden mapping and manual Excel checks). The M scripts are statically tested only (`tests/test_queries_static.py`); they have not been executed in Excel. No workbook has been built (Step 6).
