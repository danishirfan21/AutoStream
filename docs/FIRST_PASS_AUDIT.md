# First-pass audit

## Implemented

- Async FastAPI with PostgreSQL-oriented SQLAlchemy models and Alembic migrations.
- Canonical vehicles keyed by VIN; ingestion runs/errors; immutable source payload provenance; price/mileage observations.
- CSV normalization, VIN validation, fixture-driven import endpoint, health/readiness endpoints, and basic vehicle queries.
- Deterministic CSV v1/v2/invalid fixtures and unit coverage for normalization.

## Correctness changes in this pass

- The original PostgreSQL upsert updated every existing canonical vehicle for any changed source payload. It could change `updated_at` for price-only changes and relied on SQLAlchemy's `onupdate`, which is not automatically applied by `ON CONFLICT DO UPDATE`.
- The importer now compares canonical descriptive fields before issuing an update. A canonical change explicitly uses PostgreSQL `now()` for `updated_at`; price and mileage remain observations and do not alter it.
- Exact replay is checked by source name, normalized VIN source record ID, and deterministic raw-payload hash before a vehicle update or observation insert.
- Per-row work is wrapped in a nested transaction. A database constraint failure rolls back only that row's savepoint; the error is persisted by the outer transaction and later valid rows can continue.
- An unreadable/unparseable feed marks its ingestion run `failed`, stores its error message, and preserves the run. Invalid individual rows leave a run `completed` with `invalid_records` incremented.

## Counts and fixture semantics

`inserted_records` counts new canonical vehicles. `updated_records` counts changed source payloads for an existing VIN (whether or not the canonical descriptive fields changed). `duplicate_records` counts exact source-payload replays. v2 contains one exact replay (Ford), a price/mileage change (Honda), a canonical trim change (Tesla), and one new VIN (Ford Fusion).

## Index review

`vehicles.vin` has a PostgreSQL UNIQUE constraint, which creates a B-tree unique index. The initial standalone `ix_vehicles_vin` was redundant. A new migration removes it while preserving committed migration history. The make/model/year and observation/source indexes remain for their distinct query patterns.

## Remaining performance considerations

The clear baseline still performs up to two read queries per non-replayed row: one to detect exact source provenance and one to retrieve the canonical vehicle. This intentionally favors understandable semantics and correct timestamp handling over an unverified bulk pipeline. PostgreSQL `INSERT ... ON CONFLICT DO NOTHING` is used for observations. Bulk batching and reducing lookup round trips remain future work after this verifier is green.

## Unverified here

The repository has not been exercised against Docker PostgreSQL in this local environment because Docker is unavailable. The Codespaces verifier and PostgreSQL integration test are supplied for that verification; no PostgreSQL success is claimed in this audit.
