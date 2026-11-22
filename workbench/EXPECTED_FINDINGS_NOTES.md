# Expected findings: derivation notes (DRAFT, revision 2, for review)

Status: **draft, not approved**. Nothing in `workbench/` is wired into AutoStream; no application code, schema, API, frontend or fixture was changed.

This file is the specification that the future detection logic and the Excel workbook must reproduce. It was written from the fixtures, not from detector code (none exists yet).

## Scope of the data

- Fixtures: `fixtures/dealer_feed_v1.csv`, `dealer_feed_v2.csv`, `invalid_feed.csv`, `marketplace_feed.json`.
- Canonical ingestion sequence (from `scripts/verify_codespaces.sh` and `backend/tests/test_postgres_integration.py`): (1) v1, (2) v1 replay, (3) v2, (4) invalid_feed, (5) marketplace, (6) marketplace replay.
- Counts already asserted by the existing verifier: 5 vehicles, 9 accepted source records, 9 price observations. An independent stdlib cross-check of the fixtures reproduced 9 distinct accepted payloads.
- The fixtures contain **no timestamp ties and no missing source timestamps** (checked). The tie and missing-timestamp rules below are therefore specified but **not exercised by any fixture**; testing them later needs constructed inputs labelled synthetic.

## Three different questions (kept separate on purpose)

| Column | Question | Values |
|---|---|---|
| `confirmed_invalid_input` | Does the input objectively violate a stated rule? | `yes` (VIN not 17 characters; price not numeric), `undetermined` (two values disagree and nothing says which is wrong), `not_applicable` |
| `assessment` | What do the data support? | see below |
| `confirmed_pipeline_defect` | Does this finding demonstrate that AutoStream behaved incorrectly against its own documented behavior? | `none_demonstrated` on every row |

`confirmed_pipeline_defect` was renamed from `confirmed_error`. `none_demonstrated` means only that this finding does not show a pipeline defect; it does **not** assert the pipeline is correct. Known pipeline limitations from the repository review (for example the positional `row-4` record ID, error rows re-added on every replay, or whole-record rejection for one bad field) are design limitations, are not findings here, and are not claimed as defects.

`assessment` values:
- `SUSPICIOUS_REQUIRES_INVESTIGATION`: stored values disagree in a way that warrants a human look. Not proven corruption.
- `OBSERVED_CHANGE_UNVERIFIED`: a value changed over time; it may be a correction.
- `EXPECTED_REJECTION`: the pipeline rejected a deliberately invalid fixture row.
- `COVERAGE_OBSERVATION`: a VIN is present in one source's accepted records only.

`evidence_class`:
- `SOURCE_DISCREPANCY`: visible in stored values regardless of fixture origin.
- `REJECTED_INPUT`: result of a deliberate invalid fixture row.
- `COVERAGE_EXPLAINED`: the gap has a matching rejected record.
- `COVERAGE_FIXTURE_LIMITED`: **caused by limited synthetic fixtures; not a source defect.**

`counts_as_actionable` (`yes`/`no`) marks findings that count toward actionable defect counts. Proposed rule: `yes` only for `SOURCE_DISCREPANCY` findings (stored values disagree or change). `no` for fixture-limited coverage gaps (required), for the explained gap (counted through its rejection), and for the three deliberate rejected inputs (the pipeline already handled them; on real data a rejection would normally be actionable, which the reviewer may prefer). **Expected actionable count: 4 of 10.**

## Finding ID rules (stable across database rebuilds and replays)

IDs use **only feed-supplied values and semantic rule identifiers**: VIN text, source name, source record or listing ID, the source's own timestamp strings, and rule IDs defined in this file. They never use database-generated values (UUIDs, `ingested_at`, run IDs, `created_at`, payload hashes) and never use library exception names. A replay adds no accepted source records or observations (exact-replay dedup), so it cannot create or change a finding.

| Type | ID shape | Identifies |
|---|---|---|
| MILEAGE_REGRESSION | `TYPE\|vin\|source\|source_record_id\|timestamp` of the **later** observation | the event |
| ATTR_CONFLICT | `TYPE\|vin\|field\|sourceA~sourceB` (sources sorted) | the standing disagreement between each source's latest record |
| ATTR_DRIFT | `TYPE\|vin\|field\|source\|timestamp` of the **later** version | the change event |
| COVERAGE_GAP | `TYPE\|vin\|missing:source` | the missing presence |
| REJECTED_RECORD | `TYPE\|source\|record key\|rule_id\|payload timestamp` | one distinct rejected input |
| AMBIGUOUS_ORDER (specified, not in fixtures) | `TYPE\|vin\|source-or-*\|timestamp` | records that cannot be ordered |

IDs name what is asserted, not the values, so a changed value keeps the same ID and the investigation log can flag "evidence changed since logged".

### Rejected records: one ID per distinct input

Rule IDs are semantic constants: `VIN_FORMAT` (VIN is not 17 allowed characters) and `PRICE_NUMERIC` (price text is not numeric). The pipeline's exception class (`ValidationError`, `InvalidOperation`) is kept **only as evidence** (`pipeline_error_type_evidence`). Repeated occurrences of the same rejected input share one Finding ID because the ID contains only the source, record key, rule ID and the payload's own timestamp. The record key is the dealer `vin` text or the marketplace `listing_id` read from the stored payload, **not** the stored `source_record_id`, which is the positional `row-4` for the marketplace row. A missing payload timestamp is written as the literal `NO_SOURCE_TIMESTAMP`.

Each fixture rejected row violates exactly one rule (checked: INVALIDVIN has a valid price; the Altima row has a 17-character VIN; BADVIN has a valid price), so rule assignment is unambiguous here. In general the pipeline stores only the **first** failure it hits (price is parsed before the VIN is validated), so a row with both defects would be classified by evaluation order. That is a limitation of the evidence, not something to guess around.

**Future mapping risk:** deriving `rule_id` from stored errors will need a mapping from the stored error (type plus message pattern) to a rule. An unmapped error must be reported with rule `UNCLASSIFIED`, never guessed. The mapping is a later-step design item; this file does not define it.

## Distinct records versus occurrences

There are **3 distinct rejected records** (3 REJECTED_RECORD findings, 3 Finding IDs) and **4 rejection occurrences** (`EXPECTED_REJECTION_OCCURRENCES.csv`). `mk-invalid` is rejected on first ingest and again on replay because `ingest_feed` adds a new error row on every run; both occurrences carry the same Finding ID. The distinct count is invariant; the occurrence count is only valid for the canonical sequence above.

## "Latest record" and ordering rules (source-provided time only)

1. Ordering uses the **source-provided timestamp** (`updated_at` / `updated`, stored as `source_timestamp`). Ingestion time, row order, database IDs and the pipeline's `now()` fallback for `observed_at` are never used.
2. ATTR_CONFLICT compares the latest record per source for each VIN: the record with the greatest source timestamp.
3. **Equal greatest timestamps** within one (VIN, source): if the records differ on the compared field, no record is selected. The detector must emit an `AMBIGUOUS_ORDER` finding and must not emit or suppress an ATTR_CONFLICT for that pair. If the tied records agree on the field, there is no ambiguity.
4. **Missing timestamp**: a record without a source timestamp cannot be ordered. If a (VIN, source) has exactly one record it is used and its missing timestamp is shown as evidence; if it has more than one record and ordering depends on a missing timestamp, emit `AMBIGUOUS_ORDER`. The same two rules apply to MILEAGE_REGRESSION's "previous observation".
5. Because the pipeline substitutes the ingestion time for a missing timestamp when writing `observed_at` [V: `ingestion.py`], ordering must read `vehicle_source_records.source_timestamp` (which stays null), not `observed_at`.
6. Descriptive fields are compared after trimming whitespace and are case-sensitive; any normalization beyond that is a later design decision.

## How each finding was derived

| Finding | Derivation from the fixtures |
|---|---|
| Honda mileage regression | VIN 1HGCM82633A004352 in source-time order: dealer 12400 (2026-01-10), dealer 12800 (2026-02-10), marketplace mk-1001 12100 (2026-08-01). The last step decreases. |
| F-150 mileage regression | 1FTFW1E50PFA12345: dealer 18300 (2026-01-10; identical replay in v2), marketplace mk-1002 18100 (2026-08-01). |
| Honda trim conflict | Latest dealer record (2026-02-10) trim EX versus marketplace mk-1001 variant EX-L; year, make and model agree. |
| Tesla trim drift | Same dealer record ID, v1 "Long Range" then v2 "Long Range AWD". |
| Coverage: Tesla, Fusion | Present only in dealer feeds; no marketplace record or rejected record. Fixture-limited. |
| Coverage: Altima | Accepted only from marketplace mk-1003; dealer row exists in invalid_feed row 2 and was rejected. |
| Rejections (3) | invalid_feed rows 1 and 2 and marketplace element 4. |

Verification of the derivation: a stdlib-only script (not saved in the repo) re-derived the same detections and checked for ties and missing timestamps; running the existing `normalize_record` on each invalid row confirmed the stored error types and record IDs. Neither used detector logic.

## Assumptions

1. Mileage is in miles in both sources (the marketplace field is `odometer_miles`; the dealer field `mileage` has no unit).
2. A source timestamp is when the record was updated, not when the odometer was read. A lower mileage in a later record is therefore only suspicious.
3. A "previous observation" for mileage means the immediately earlier observation for the same VIN across all sources, ordered by source timestamp.
4. No root cause is asserted for any finding. The fixtures are synthetic, so causes (typo, unit difference, stale data, different vehicle condition and so on) cannot be determined from them.

## Ambiguities and candidates deliberately **excluded**

- **Different locations across sources.** Honda "Austin TX" versus "Dallas, TX"; F-150 "Dallas TX" versus "Fort Worth, TX". These may be genuinely different places. "Dallas TX" versus "Dallas, TX" also shows inconsistent punctuation between feeds. Candidate rule only.
- **Price differences across sources** (Honda 27900 versus 27950; F-150 41500 versus 40800). Market variation is expected and any threshold would be arbitrary.
- **Unchanged Tesla mileage and price** between v1 and v2 while the timestamp advanced. No rule defines this as an issue.
- **F-150 v2 row** is an exact replay of v1 (timestamp not advanced), so the dealer record is unchanged since 2026-01-10.
- **VIN check digit.** Three of the five fixture VINs fail the standard North American check digit (1FTFW1E50PFA12345, 3FA6P0H73HR123456, 1N4AL3AP9JC123456). Excluded: the pipeline does not validate it and the fixtures are synthetic.
- **Honda trim.** EX and EX-L are different trims; it is unknown which is correct.
- **Dealer versions share one `source_record_id`** (the VIN), so versions are distinguished by source timestamp only.

## Expected totals

| Measure | Value |
|---|---|
| Findings | 10 |
| Actionable (`counts_as_actionable = yes`) | 4 (2 mileage regressions, 1 trim conflict, 1 trim drift) |
| Not actionable | 6 (3 rejected inputs, 2 fixture-limited gaps, 1 explained gap) |
| Distinct rejected records | 3 |
| Rejection occurrences (canonical sequence) | 4 |

## Decisions still open for the reviewer

1. Is the proposed `counts_as_actionable` rule right, in particular `no` for the three deliberate rejected inputs?
2. Approve `AMBIGUOUS_ORDER` as a specified-but-unexercised finding type, and the rule that equal timestamps are never silently resolved?
3. Approve the rule identifiers `VIN_FORMAT`, `PRICE_NUMERIC`, `MILEAGE_NON_DECREASING`, `ATTR_CROSS_SOURCE_AGREEMENT`, `ATTR_SAME_SOURCE_STABILITY` and `SOURCE_COVERAGE`?

## Constraint for future integration tests

`backend/tests/test_postgres_integration.py` runs `TRUNCATE` against whatever `DATABASE_URL` points to. Workbench extract tests must **never** reuse the Compose development or verifier database. They must create and drop their own disposable database. No database operation of any kind has been run for this work.
