# AutoStream Performance Evidence

## Environment and methodology

Measured in one GitHub Codespaces `basicLinux32gb` environment with PostgreSQL 16, Python 3.11, Docker Compose, and localhost HTTP. The opt-in generator used a fixed seed and loaded 10,000 synthetic canonical vehicles, 30,000 source records, and 64,984 price observations in 11.696 seconds. These records are synthetic, not market data.

Each endpoint received one warmup and 30 sequential localhost HTTP requests. Results are median and p95 latency; they are not a concurrency or production-load claim.

## Results

| Operation | Median | p95 | Notes |
|---|---:|---:|---|
| VIN lookup | 2.683 ms | 6.042 ms | unique VIN B-tree |
| Make-filtered listing | 3.587 ms | 3.814 ms | `(make, model, year)` B-tree prefix |
| Provenance | 3.336 ms | 5.511 ms | vehicle-ID index |
| Price history | 3.277 ms | 3.649 ms | vehicle-ID lookup |
| Market snapshot | 2.833 ms | 3.662 ms | VIN lookup plus per-VIN observations |
| Market summary | 29.377 ms | 31.015 ms | latest-observation aggregate |

## Query-plan evidence and improvement

VIN lookup used `vehicles_vin_key` (0.082 ms database execution); provenance used `ix_vehicle_source_records_vehicle_id` (0.078 ms). The baseline latest-observation aggregate used `ix_vehicle_price_observations_vehicle_id` plus incremental sort and completed in 38.440 ms on 64,984 rows.

Migration `0004_observation_latest_index` adds `(vehicle_id, observed_at DESC, id DESC)`. The post-index aggregate plan uses `ix_observations_vehicle_latest` and completed in 15.600 ms under the same generated scale. This is a targeted 22.840 ms reduction in the captured database plan. Per-VIN lookup still performs a tiny in-memory sort over nine rows, so no additional index was added. The tradeoff is extra index storage and write maintenance for price observations.

Detailed captured plans are in [performance](performance/).

## Limitations

Synthetic data, one Codespaces machine, sequential localhost requests, no distributed clients, no sustained workload, and no production cache layer. AutoStream is not a valuation model.
