# AutoStream interview notes

- **Why canonical VINs?** A VIN is the shared vehicle identity across feeds; it prevents duplicate canonical vehicles.
- **Why provenance separately?** It retains the original source records and historical versions without overwriting source truth.
- **Why observations separately?** Price, mileage, and location change over time and are therefore history, not canonical attributes.
- **How is replay idempotent?** Source payload hashes and observation uniqueness make an exact re-import a no-op.
- **How are conflicts handled?** A later cross-source payload does not overwrite established non-null canonical fields.
- **Why separate NHTSA enrichment?** It is external reference data with its own failure and replay semantics.
- **How is latest price selected?** Deterministically by `observed_at DESC, id DESC`.
- **Why Decimal strings?** Exact money avoids binary floating-point ambiguity at the API boundary.
- **What did EXPLAIN reveal?** VIN/provenance used existing indexes; the global latest-observation aggregate sorted 64,984 rows.
- **What index tradeoff was accepted?** The composite latest-observation index reduced the captured aggregate plan from 38.440 to 15.600 ms, at write/storage cost.
- **At 10x scale?** Re-measure real workloads, pagination, retention, and aggregate strategy before adding infrastructure.
- **When Redis or workers?** Only after measured repeated-read or asynchronous-work bottlenecks.
- **What remains unimplemented?** Authentication, production deployment, distributed caching/queues, and predictive valuation.
