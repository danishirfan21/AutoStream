# Power Query (M) scripts

Twenty `.pq` files. Each file is the body of one Power Query query: open **Data → Get Data → Launch Power Query Editor → New Source → Blank Query → Advanced Editor**, paste the file, name the query exactly as the file (without `.pq`).

> **Status: written and statically checked, NOT yet executed in Excel.** No Power Query engine was available when these were written. `tests/test_queries_static.py` checks structure (balanced delimiters, dependency graph is acyclic, column list equals the golden header, Python literals present, no hard-coded paths, no database functions). It cannot prove the M evaluates correctly. Run `../VERIFICATION_CHECKLIST.md` in desktop Excel before trusting any output.

The only data source is the committed CSV files in `workbench/sample/`. No database, no AutoStream process.

## Dependency graph

```
DataFolder (parameter) ──► Raw_SourceRecords ──► SourceRecords ─┬─► F_Mileage ──────────┐
                      ├──► Raw_IngestionErrors ───────────────┤  ├─► F_AttributeFindings ─┤
                      ├──► Vehicles                            │  ├─► F_Rejected ─► F_Coverage ─┤──► Findings ──► Checks
                      ├──► PriceObservations                   │  ├─► F_Ambiguous ─────────┘
                      └──► IngestionRuns                       │  └─► VinSourceLatest
SyntheticFixtureMode (parameter) ─► F_Rejected, F_Coverage
SourceMap (record), Lib (helper record) ─► used by SourceRecords and all F_* queries
ExpectedFindingsPath (parameter) ──► ExpectedFindings   (optional golden check)
```

## Creation order (dependencies first)

1. `DataFolder`, `SyntheticFixtureMode`, `ExpectedFindingsPath` (parameters; paste as Blank Query, the `meta [...]` marks them as parameters)
2. `SourceMap`, `Lib`
3. `Raw_SourceRecords`, `Raw_IngestionErrors`, `Vehicles`, `PriceObservations`, `IngestionRuns`, `ExpectedFindings`
4. `SourceRecords`
5. `F_Mileage`, `F_AttributeFindings`, `F_Rejected`, `F_Coverage`, `F_Ambiguous`
6. `Findings`, `VinSourceLatest`, `Checks`

If you create a query before its dependency Excel shows "name not recognized"; create the dependency and refresh.

## Load destinations

| Query | Load as | Table name |
|---|---|---|
| `Findings` | Table on sheet | `tblFindings` |
| `SourceRecords` | Table on sheet | `tblSourceRecords` |
| `VinSourceLatest` | Table on sheet | `tblLatest` |
| `Checks` | Table on sheet | `tblChecks` |
| `IngestionRuns` | Table on sheet | `tblRuns` |
| `Vehicles` | Table on sheet | `tblVehicles` |
| `PriceObservations` | Table on sheet (optional) | `tblPrices` |
| `ExpectedFindings` | Table on sheet (optional golden check) | `tblExpected` |
| all others | **Only Create Connection** | – |

Excel names the table after the query; rename via Table Design → Table Name.

## What each query does

| Query | Purpose |
|---|---|
| `DataFolder` | Parameter: absolute path of the `sample` folder. The only place a path lives. |
| `SyntheticFixtureMode` | Parameter, default `false`. `true` reproduces the golden file's classification (see below). |
| `SourceMap` | Per-source JSON field names (dealer_csv, marketplace_json); mirrors `rf.SOURCES`. |
| `Lib` | Shared helpers: normalization, timestamp grouping, ambiguity detection, 24-column schema. |
| `Raw_*`, `Vehicles`, `PriceObservations`, `IngestionRuns` | Straight CSV loaders; everything text except run counts; no coercion; missing columns raise errors. |
| `SourceRecords` | One row per source record. VIN stays text; original `source_timestamp_utc` text kept; adds parsed `ts`, `year/make/model/trim/mileage`. Bad values stay visible (parsed column null, original kept). |
| `F_Mileage` | Per VIN, orders records by source timestamp; same-timestamp groups that disagree are AMBIGUOUS (skipped); flags a later lower mileage. |
| `F_AttributeFindings` | `ATTR_CONFLICT` (latest per source disagree) and `ATTR_DRIFT` (same source changes over time). |
| `F_Rejected` | One row per distinct rejected payload; classifies rule from the error text; carries `distinct_record_count` and `occurrences_canonical_sequence`. |
| `F_Coverage` | `COVERAGE_GAP` per (VIN, missing source), linked to a rejected finding when one explains it. |
| `F_Ambiguous` | `AMBIGUOUS_ORDER` where ordering cannot be decided (0 rows on the sample). |
| `Findings` | Union of the above, 24 columns, text, errors on duplicate `finding_id`. |
| `VinSourceLatest` | Latest record per (VIN, source) for XLOOKUP; blank values (never a guess) when tied-and-different or unorderable. |
| `Checks` | Seven PASS/REVIEW integrity checks (unparseable timestamps, VIN length, reject accounting, ...). |

## Semantics kept identical to `reference_findings.py`

- Ordering uses **source timestamp only** (never ingestion time or row order). Equal timestamps that disagree on a compared field are ambiguous and no regression/conflict/drift is reported for them.
- Two or more records with any missing timestamp: unorderable → `AMBIGUOUS_ORDER|vin|scope|NO_SOURCE_TIMESTAMP`.
- Rejected findings count **distinct** payloads (3), while `occurrences_canonical_sequence` counts log occurrences (4). These are never merged.
- Every finding is an anomaly flag warranting investigation. `confirmed_pipeline_defect` is `none_demonstrated` on all rows; `counts_as_actionable` means "warrants investigation".

## SyntheticFixtureMode

| Mode | Unexplained coverage gaps | Rejected records | Actionable on the sample |
|---|---|---|---|
| `false` (default, real data) | `COVERAGE_UNEXPLAINED`, actionable | `counts_as_actionable = yes` | 9 (2 mileage + 1 conflict + 1 drift + 3 rejected + 2 coverage) |
| `true` (the committed golden file) | `COVERAGE_FIXTURE_LIMITED`, not actionable (the sample is a tiny synthetic fixture, so absence is an artefact) | `no` (evidence class stays `REJECTED_INPUT`) | 4 |

Rule: set `true` **only** to compare against `EXPECTED_FINDINGS.csv`. The 10 finding IDs are identical in both modes; only the classification columns differ.

## Known risks (verify in Excel)

Listed with how to test them in `../VERIFICATION_CHECKLIST.md`: empty ranges `{0..n-2}` when n < 2; `Json.Document(Text.ToBinary(...))`; `DateTimeZone.FromText` with `Z`; whether empty CSV fields arrive as null or `""`; comparer functions in `List.Sort`; formula-firewall behaviour; Windows backslash paths (Mac needs different paths); raw-JSON-text comparison for distinct payloads (Python normalizes with sorted keys); JSON null renders as `None` (same as Python).
