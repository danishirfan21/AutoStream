# Verification checklist and golden-findings mapping

## A. What was and was not tested

| Area | Status |
|---|---|
| Python reference detector reproduces the 10 golden findings | **Tested** (`tests/test_reference_findings.py`, `tools/golden_compare.py`) |
| SQL extracts vs real PostgreSQL | **Tested** opt-in (`WORKBENCH_PG_INTEGRATION=1`, disposable cluster) |
| 20 `.pq` files: structure, parameters, dependency graph acyclic, no machine paths, no database functions, schema equals golden header, Python literals present, finding-id templates, self-reference lint | **Tested** statically (`tests/test_queries_static.py`) |
| M evaluates without errors in Excel | **NOT tested** (no Power Query engine here) |
| M produces the same 10 rows as the golden file | **NOT tested** |
| Any Excel formula, Table, PivotTable, conditional format in the guides | **NOT tested**; written from documentation knowledge |
| Refresh behavior, pivot refresh order, spill behavior, log formulas | **NOT tested** |

A static pass means "plausible", not "works". Do not report the workbook as verified until every box below is ticked in desktop Excel.

## B. Golden-findings mapping (10 findings)

IDs are identical in both `SyntheticFixtureMode` settings; only the classification columns differ for rows marked †.

| # | `finding_id` | Produced by (query) | Golden class / actionable | Real-data mode (default) |
|---|---|---|---|---|
| 1 | `MILEAGE_REGRESSION\|1HGCM82633A004352\|marketplace_json\|mk-1001\|2026-08-01T10:30:00Z` | `F_Mileage` | SOURCE_DISCREPANCY / yes | same |
| 2 | `MILEAGE_REGRESSION\|1FTFW1E50PFA12345\|marketplace_json\|mk-1002\|2026-08-01T10:45:00Z` | `F_Mileage` | SOURCE_DISCREPANCY / yes | same |
| 3 | `ATTR_CONFLICT\|1HGCM82633A004352\|trim\|dealer_csv~marketplace_json` | `F_AttributeFindings[Conflicts]` | SOURCE_DISCREPANCY / yes | same |
| 4 | `ATTR_DRIFT\|5YJ3E1EA7PF123456\|trim\|dealer_csv\|2026-02-10T10:00:00Z` | `F_AttributeFindings[Drifts]` | SOURCE_DISCREPANCY / yes | same |
| 5 | `REJECTED_RECORD\|dealer_csv\|INVALIDVIN\|VIN_FORMAT\|2026-01-10T10:00:00Z` † | `F_Rejected` | REJECTED_INPUT / no | REJECTED_INPUT / yes |
| 6 | `REJECTED_RECORD\|dealer_csv\|1N4AL3AP9JC123456\|PRICE_NUMERIC\|2026-01-10T10:00:00Z` † | `F_Rejected` | REJECTED_INPUT / no | REJECTED_INPUT / yes |
| 7 | `REJECTED_RECORD\|marketplace_json\|mk-invalid\|VIN_FORMAT\|2026-08-01T11:15:00Z` † (2 occurrences) | `F_Rejected` | REJECTED_INPUT / no | REJECTED_INPUT / yes |
| 8 | `COVERAGE_GAP\|5YJ3E1EA7PF123456\|missing:marketplace_json` † | `F_Coverage` | COVERAGE_FIXTURE_LIMITED / no | COVERAGE_UNEXPLAINED / yes |
| 9 | `COVERAGE_GAP\|3FA6P0H73HR123456\|missing:marketplace_json` † | `F_Coverage` | COVERAGE_FIXTURE_LIMITED / no | COVERAGE_UNEXPLAINED / yes |
| 10 | `COVERAGE_GAP\|1N4AL3AP9JC123456\|missing:dealer_csv` | `F_Coverage` (links finding 6) | COVERAGE_EXPLAINED / no | same |

Expected totals: 10 findings; 3 distinct rejected records but 4 occurrences (`distinct_record_count` 1 on each rejected row, `occurrences_canonical_sequence` total 4); `AMBIGUOUS_ORDER` 0; `Checks` all PASS. Actionable: 4 with `SyntheticFixtureMode = true`, 9 with `false`.

## C. Manual verification in desktop Excel

Tick each item; note differences.

**Loading and parameters**
- [ ] V-01 Paste all 20 queries in the documented order; none shows an error step.
- [ ] V-02 `DataFolder` appears as a parameter; changing it and refreshing switches the data source; no other file contains a path.
- [ ] V-03 Refresh succeeds with no "Formula.Firewall" error (parameter queries are used in `File.Contents`; if firewall errors appear, record the query and the message).
- [ ] V-04 `tblSourceRecords`: 9 rows; `vin` is text and keeps 17 characters; `source_timestamp_utc` shows the original ISO text; `ts` is a UTC datetimezone (`DateTimeZone.FromText` accepts the `Z` suffix); `mileage` numeric.
- [ ] V-05 Empty CSV fields: in `Raw_*` tables check whether empties are null or `""` and that findings and `tblLatest` treat them as missing (no errors).
- [ ] V-06 `Json.Document(Text.ToBinary(...))` parses every `raw_payload_json`; `year/make/model/trim/mileage` match the payload for both sources.

**Findings**
- [ ] V-07 `tblFindings` has exactly the 10 ids in section B (compare with `EXPECTED_FINDINGS.csv`, section 9 of the guide); columns in golden order; no duplicates.
- [ ] V-08 Switching `SyntheticFixtureMode` flips the † rows as shown; actionable counts 9 / 4.
- [ ] V-09 `Refresh All` twice leaves pivots consistent with `tblFindings`.
- [ ] V-09a Edge behavior: empty range `{0..n-2}` for a VIN with 1 record does not error (sample: Fusion, Altima have 1 record). Also records with a single timestamp group.
- [ ] V-09b Mutation tests on a **copy** of the sample folder: (1) two records with the same timestamp but different mileage → `AMBIGUOUS_ORDER`, no regression; (2) remove a timestamp from one of two records of one VIN/source → `AMBIGUOUS_ORDER|…|NO_SOURCE_TIMESTAMP`; (3) a payload with an invalid mileage text stays visible and does not crash; (4) same-source different record id with identical timestamp. Compare each with the Python detector's result for the same edit.

**Worksheet features**
- [ ] V-10 `Reconcile` spills, shows `CONFLICT` for the Honda trim, `marketplace LOWER` for Honda and F-150 mileage, `NO RECORD` where a source is missing.
- [ ] V-11 `Scorecard` figures match section B.
- [ ] V-12 PivotTables (findings by issue type × actionable; status) refresh and use table names, not fixed ranges.
- [ ] V-13 Investigation log: log two findings, refresh, both `OK`; edit a copy of the data so one disappears → `DISAPPEARED`; log rows untouched; triage spill lists the rest. Confirm `InvestigationLog` is not part of any query load destination.
- [ ] V-14 Conditional formats trigger on the expected rows and keep working after refresh (apply to ranges, not to a spill address).
- [ ] V-15 Golden check sheet: 10 found, 0 missing, 0 extra, class and actionable columns TRUE (in `SyntheticFixtureMode = true`).

**Compatibility**
- [ ] V-16 Record the Excel build (File → Account) and whether `LET`, `BYROW`, `LAMBDA`, `XLOOKUP`, `FILTER`, `UNIQUE`, `SORT` are available.
- [ ] V-17 Save as `.xlsx`, reopen, refresh with the path unchanged; then move the workbook to another folder and confirm only `DataFolder` needs changing.
- [ ] V-18 Known limitations accepted: Windows backslash paths (Mac needs separators changed), `Table.Sort` is culture-based (display only; `finding_id` identity unaffected).

## D. Likely failure points and where to look

| Symptom | Probable cause | Fix |
|---|---|---|
| `Expression.Error: The name 'Lib' wasn't recognized` | queries created out of order or renamed | create/rename exactly as in `queries/README.md` |
| `DataSource.NotFound` | `DataFolder` wrong or has trailing backslash | fix the parameter |
| Embedded newline breaks rows | `QuoteStyle.Csv` missing | keep it in all CSV loaders |
| `Formula.Firewall` | query combines data sources | see V-03; use *Ignore privacy levels* in Query options for this workbook if acceptable |
| Spill `#SPILL!` | cells under the formula not empty | clear the cells below |
| `#NAME?` | `LET`/`XLOOKUP`/`BYROW` unavailable | Microsoft 365 required |
| `Checks` REVIEW | a real data anomaly, not necessarily a defect | read the row |
