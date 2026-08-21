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

The API image now builds from repository root, packages the canonical fixture directory at `/app/fixtures`, and receives `FIXTURES_DIR=/app/fixtures`. Local execution retains the repository-root default. The latest run confirmed fixture packaging, reached the application persistence path, and received `201 Created` from the v1 CSV endpoint. It then failed before persistence assertions because several verifier calls passed literal escaped double quotes (`\"SELECT`) into `psql`, producing an unterminated quoted identifier. The verifier now uses one `psql_scalar` helper with `ON_ERROR_STOP` and named scalar assertions that print expected/actual values. Codespaces rerun is pending. The command is:

```bash
./scripts/verify_codespaces.sh
```

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
