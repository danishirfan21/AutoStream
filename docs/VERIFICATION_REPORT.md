# Verification report

## Commands actually run in this environment

```text
python -m compileall -q backend/app backend/alembic
PYTHONPATH=backend python -m pytest backend/tests -q
```

Current local result: `7 passed, 1 skipped`. The skipped test is intentionally PostgreSQL-only and requires `RUN_POSTGRES_INTEGRATION=1`.

## Codespaces / PostgreSQL status

The Codespaces verifier was run through Docker/Compose startup and PostgreSQL health, but the API failed during Alembic startup with `ModuleNotFoundError: No module named 'psycopg2'`.

Root cause: `backend/alembic/env.py` stripped `+asyncpg` from the configured `DATABASE_URL` and used synchronous `engine_from_config`. SQLAlchemy consequently selected its default synchronous PostgreSQL dialect (`psycopg2`) despite the application and Compose configuration using `postgresql+asyncpg://`.

The migration environment now retains the asyncpg URL and uses `async_engine_from_config` with `connection.run_sync(...)`. The unused synchronous `psycopg` dependency was removed.

## Latest Codespaces progress

The latest run confirmed Docker image build, PostgreSQL startup/health, async Alembic migrations (`0001` and `0002`), FastAPI startup, and successful `/health` and `/ready` responses. It then failed with `404 Not Found` for `dealer_feed_v1.csv` because the API image was built from the `backend/` context and did not contain the repository-root `fixtures/` directory.

The API image now builds from repository root, packages the canonical fixture directory at `/app/fixtures`, and receives `FIXTURES_DIR=/app/fixtures`. Local execution retains the repository-root default. The latest run confirmed fixture packaging, reached the application persistence path, and received `201 Created` from the v1 CSV endpoint. It then failed before persistence assertions because several verifier calls passed literal escaped double quotes (`\"SELECT`) into `psql`, producing an unterminated quoted identifier. The verifier now uses one `psql_scalar` helper with `ON_ERROR_STOP` and named scalar assertions that print expected/actual values.

That corrected verifier then reached all live API checks: v1 ingestion, exact replay, v2 ingestion, invalid-feed ingestion, error lookup, and vehicle lookup. Its PostgreSQL integration test alone failed because the test independently resolved fixtures as `/fixtures` inside the image. Tests now use the same configured fixture resolver as the API (`FIXTURES_DIR` in Docker, repository-root default locally), assert fixture availability, and assert every direct ingestion run completed before checking counters. Codespaces rerun is pending. The command is:

```bash
./scripts/verify_codespaces.sh
```

## Verified CSV baseline

The Codespaces verifier completed the CSV baseline successfully: Docker/Compose, PostgreSQL, async Alembic migrations, FastAPI health/readiness, deterministic CSV imports, exact replay, incremental update, persistence, error handling, and PostgreSQL integration tests.

## Multi-source status

The next verifier revision adds `marketplace_feed.json`: three valid listings (two VINs overlapping CSV and one new VIN) plus one invalid VIN. It verifies VIN-level deduplication, independent `marketplace_json` provenance using listing IDs, source observation history, the non-overwrite cross-source conflict rule, and JSON replay. This multi-source verifier has not yet been run in Codespaces.

The first multi-source rerun reached JSON ingestion and proved the shared Honda VIN has three provenance rows: dealer v1, changed dealer v2, and marketplace listing `mk-1001`. The prior verifier expected two rows and was incorrect because changed same-source payloads are intentionally historical provenance. It now asserts one canonical Honda vehicle, two dealer provenance versions, one marketplace provenance row, and three observations; the canonical trim remains dealer `EX` while JSON `EX-L` stays in source payload provenance. A follow-up rerun is pending.

The intelligence verifier then proved deterministic NHTSA enrichment/replay and market summary, but failed at market snapshot because the joined query used ambiguous `ORDER BY observed_at DESC, id DESC`. The query now qualifies the intended deterministic ordering as `o.observed_at DESC, o.id DESC`; a Codespaces rerun is pending.

Commit `068bf10` fixed that SQL ambiguity and the following Codespaces run returned the expected deterministic market snapshot. The remaining verifier-only failure compared Decimal-backed monetary JSON strings (for example `"27950.00"`) to an integer. The verifier now uses `Decimal` for monetary assertions and tolerance for the percentage calculation; rerun pending.

The next run reached the PostgreSQL integration suite, where its snapshot test still made the same stale integer assumption. It now uses `Decimal` for exact money and `pytest.approx` for percentage change; rerun pending.

That script starts the Compose stack, applies Alembic migrations through the API startup, verifies v1, exact replay, v2, persisted row counts, timestamp semantics, invalid-row error persistence, API lookup, and the PostgreSQL integration test. It exits non-zero for any failed assertion.

## Expected deterministic counts (not yet a claimed run result)

| Import | Inserted | Updated | Duplicate | Invalid |
| --- | ---: | ---: | ---: | ---: |
| `dealer_feed_v1.csv` | 3 | 0 | 0 | 0 |
| identical v1 replay | 0 | 0 | 3 | 0 |
| `dealer_feed_v2.csv` | 1 | 2 | 1 | 0 |
| `invalid_feed.csv` | 0 | 0 | 0 | 2 |

## Known limitations

- Only the CSV ingestion baseline is included.
- No JSON/NHTSA adapters, caching, analytics, frontend, queues, or load tests are implemented.
- The current row-by-row implementation is intentionally not a batch-ingestion benchmark.
