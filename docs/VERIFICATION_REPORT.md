# Verification report

## Commands actually run in this environment

```text
python -m compileall -q backend/app backend/alembic
PYTHONPATH=backend python -m pytest backend/tests -q
```

Current local result: `5 passed, 1 skipped`. The skipped test is intentionally PostgreSQL-only and requires `RUN_POSTGRES_INTEGRATION=1`.

## Codespaces / PostgreSQL status

Not run in this environment: Docker is not installed, so neither Docker Compose nor a PostgreSQL server was available. The actual end-to-end command is:

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
