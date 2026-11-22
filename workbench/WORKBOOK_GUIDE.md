# Building the Data Quality Workbench in desktop Excel

**Audience:** someone who has used Excel but never Power Query. **Needs:** desktop Excel for Windows, Microsoft 365 (dynamic arrays, `XLOOKUP`, `LET`, `SORT`, `UNIQUE`). Excel 2016/2019 lacks these functions. Excel for the web cannot edit Power Query; Mac Excel has limited Power Query and the `DataFolder` path would need a Mac path (the M files use `\`).

> **Status:** this guide and the M scripts were written without access to Excel. Nothing here has been run. Work through `VERIFICATION_CHECKLIST.md` as you go; if a step behaves differently, trust Excel and record the difference. Step 6 (the actual `.xlsx`) has not been built.

No database and no AutoStream process is needed. The only inputs are the CSV files in `workbench/sample/`.

---

## 0. Folder and file naming

Save the workbook **outside** `sample/` (e.g. `workbench/DQ_Workbench.xlsx`, not committed until you decide). Use a **macro-free `.xlsx`**.

## 1. Create the queries

1. Open a new workbook. Data → **Get Data → Launch Power Query Editor**.
2. For each file in `queries/` in the order given in `queries/README.md`: **Home → New Source → Other Sources → Blank Query**, then **View → Advanced Editor**, delete everything, paste the file's text, **Done**, then rename the query (right-click in the Queries pane → Rename) to the filename without `.pq`.
3. **DataFolder:** paste `DataFolder.pq` as a Blank Query. The `meta [IsParameterQuery = true ...]` makes Excel show it as a parameter. If it shows as a normal query instead, use **Home → Manage Parameters → New Parameter** (Type: Text, Required) and name it `DataFolder`; the other queries refer only to the name.
4. Edit `DataFolder`'s **Current Value** to the absolute path of `workbench\sample` on your machine, no trailing backslash, e.g. `C:\path\to\AutoStream\workbench\sample`. This is the **only** place a path is stored.
5. Leave `SyntheticFixtureMode` = `false`. (Set `true` only for the golden check, section 9.)
6. For every query, check **no red error banner** and the step "Source" gives a table. Fix errors before continuing.
7. **Home → Close & Load To…** is applied per query. In the Excel **Queries & Connections** pane right-click each query → **Load To…** and choose:
   - *Table* on a new worksheet for: `Findings`, `SourceRecords`, `VinSourceLatest`, `Checks`, `IngestionRuns`, `Vehicles`, (optional) `PriceObservations`, `ExpectedFindings`.
   - *Only Create Connection* for everything else.
8. Rename tables (Table Design → Table Name): `tblFindings`, `tblSourceRecords`, `tblLatest`, `tblChecks`, `tblRuns`, `tblVehicles`, `tblPrices`, `tblExpected`.

Power Query **privacy prompt:** on first refresh Excel may ask for privacy levels for the folder; choose *Organizational/Private* or ignore privacy for this file. A "formula.firewall" error is a known risk to record (checklist item V-03).

## 2. Sheet design

| Sheet | Content | Source |
|---|---|---|
| `README` | Purpose, how to refresh, data-folder path, the status wording ("flag, not proven defect") | typed text |
| `Findings` | `tblFindings`, 24 columns | query |
| `Reconcile` | one row per VIN, side-by-side sources | XLOOKUP over `tblLatest` |
| `Scorecard` | counts, percent, checks | formulas over tables |
| `Pivots` | two PivotTables | `tblFindings`, `tblInvestigationLog` |
| `InvestigationLog` | `tblInvestigationLog` (typed by the analyst) | manual, **never a query** |
| `Checks` | `tblChecks` | query |
| `SourceRecords`, `Latest`, `Runs`, `Vehicles`, `Prices` | supporting tables | queries |
| `GoldenCheck` (optional) | `tblExpected` vs `tblFindings` | formulas |

Keep the log on its **own sheet with no query on it** so a refresh never touches it (see `INVESTIGATION_LOG.md`).

## 3. Reconcile sheet (cross-source with XLOOKUP)

Purpose: for each VIN show the latest accepted value from each source and flag disagreement. `tblLatest` already holds one row per (VIN, source) with `key = vin|source`, and leaves values **blank** (status `AMBIGUOUS_TIE` / `UNORDERABLE_NO_TS`) rather than guess.

Layout (row 1 headers; row 2 formulas; each formula **spills** down, do not fill down):

| Cell | Header | Formula |
|---|---|---|
| A2 | vin | `=SORT(UNIQUE(tblLatest[vin]))` |
| B1 | `dealer_csv` | typed text (used by the formulas) |
| C1 | `marketplace_json` | typed text |
| B2 | dealer trim | `=LET(r,XLOOKUP($A$2#&"|"&B$1,tblLatest[key],tblLatest[trim],"NO RECORD"),IF(r="","(blank)",r))` |
| C2 | marketplace trim | same formula, `C$1` instead of `B$1` |
| D2 | trim check | `=IF(($B$2#="NO RECORD")+($C$2#="NO RECORD")>0,"single source",IF(EXACT($B$2#,$C$2#),"match","CONFLICT"))` |
| E2 | dealer mileage | `=LET(r,XLOOKUP($A$2#&"|"&$B$1,tblLatest[key],tblLatest[mileage],"NO RECORD"),IF(r="","(blank)",r))` |
| F2 | marketplace mileage | same with `$C$1` |
| G2 | mileage check | `=IF(ISNUMBER($E$2#)*ISNUMBER($F$2#),IF($F$2#<$E$2#,"marketplace LOWER",IF($F$2#>$E$2#,"marketplace higher","equal")),"n/a")` |
| H2 | dealer status | `=XLOOKUP($A$2#&"|"&$B$1,tblLatest[key],tblLatest[status],"NO RECORD")` |
| I2 | marketplace status | same with `$C$1` |
| J2 | finding(s) | `=BYROW($A$2#,LAMBDA(v,TEXTJOIN("; ",TRUE,FILTER(tblFindings[issue_type],tblFindings[vin]=v,""))))` |

Notes:

- `EXACT` is used because `=` ignores case; Power Query compares case-sensitively, so Excel and M must agree. If your Excel lacks `BYROW`/`LAMBDA`, drop column J.
- The `G` check is an **exploratory view**; the authoritative mileage finding comes from `tblFindings` (it uses the full chronological history, not only the latest values).
- When the VIN appears in `AMBIGUOUS_TIE`, the value columns show `(blank)` and the status columns show why.

## 4. Scorecard

Cells with labels in column A, formulas in B. All use `tblFindings`/`tblChecks`/`tblSourceRecords`.

| Metric | Formula |
|---|---|
| Source records | `=ROWS(tblSourceRecords[vin])` |
| Distinct VINs | `=COUNTA(UNIQUE(tblSourceRecords[vin]))` |
| Findings | `=ROWS(tblFindings[finding_id])` |
| Actionable ("warrants investigation") | `=COUNTIFS(tblFindings[counts_as_actionable],"yes")` |
| Mileage regressions | `=COUNTIFS(tblFindings[issue_type],"MILEAGE_REGRESSION")` |
| Attribute conflicts | `=COUNTIFS(tblFindings[issue_type],"ATTR_CONFLICT")` |
| Attribute drift | `=COUNTIFS(tblFindings[issue_type],"ATTR_DRIFT")` |
| Rejected records (distinct) | `=COUNTIFS(tblFindings[issue_type],"REJECTED_RECORD")` |
| Rejection occurrences in log | `=SUM(IFERROR(VALUE(tblFindings[occurrences_canonical_sequence]),0))` (non-rejected rows hold `""`, which `IFERROR` turns into 0) |
| Coverage gaps | `=COUNTIFS(tblFindings[issue_type],"COVERAGE_GAP")` |
| VIN-source pairs with a clean latest value | `=COUNTIFS(tblLatest[status],"OK")` of `=ROWS(tblLatest[key])` |
| Integrity checks needing review | `=COUNTIFS(tblChecks[status],"REVIEW")` |
| Share of VINs with at least one actionable finding | `=COUNTA(UNIQUE(FILTER(tblFindings[vin],(tblFindings[counts_as_actionable]="yes")*(tblFindings[vin]<>""),""))) / B3` (adjust B3 to the Distinct-VIN cell; guard against `#CALC!` with `IFERROR(...,0)`) |

Always keep the 3 distinct rejected records and the 4 occurrences as separate lines; never sum them.

Wording on the sheet: "flags warranting investigation, not confirmed defects". Percentages describe the 6-VIN sample and are illustrative only.

## 5. Conditional formatting (anomalies)

Select the range, **Home → Conditional Formatting → New Rule → Use a formula**.

| Where | Rule formula (first cell relative) | Format |
|---|---|---|
| `tblFindings[evidence_class]` | `=$D2="SOURCE_DISCREPANCY"` (applied to the table body) | amber fill |
| `tblFindings[counts_as_actionable]` | `="yes"` cell value | bold red text |
| `Reconcile!D:D` | `=D2="CONFLICT"` | red fill |
| `Reconcile!G:G` | `=G2="marketplace LOWER"` | red fill |
| `Reconcile!B:C` | `=B2="NO RECORD"` | grey italic |
| `Reconcile!H:I` | `=AND(H2<>"OK",H2<>"NO RECORD",H2<>"")` | orange fill |
| `tblChecks[status]` | cell value = `REVIEW` | orange fill |
| `InvestigationLog` helper column | see `INVESTIGATION_LOG.md` | |

Spilled ranges: apply the rule to a generous range (e.g. `B2:J200`), not just the current spill size.

## 6. PivotTables

Use **Insert → PivotTable → From Table/Range** with the table name (never a fixed range).

1. **Findings by issue type and actionability** (source `tblFindings`): Rows = `issue_type`; Columns = `counts_as_actionable`; Values = Count of `finding_id`.
2. **Findings by evidence class** (second Pivot, same source): Rows = `evidence_class`, Values = Count of `finding_id`.
3. **Investigation status** (source `tblInvestigationLog`): Rows = `status`; Values = Count of `finding_id`; optional Columns = `issue_type_at_logging`.

Right-click each PivotTable → **PivotTable Options → Data → "Refresh data when opening the file"** on. Pivots are static between refreshes; **Data → Refresh All** refreshes queries and pivots but not necessarily in dependency order, so after a refresh that changes `tblFindings`, run **Refresh All twice** (checklist V-09).

## 7. Refresh behavior

- **Data → Refresh All** reloads all CSVs from `DataFolder`, rebuilds `tblFindings`, `tblLatest` etc.
- Tables are replaced in place; formulas referring to `tblName[col]` keep working; spills resize.
- **Do not** type inside query tables: edits are overwritten on refresh.
- Turn off *Preserve column sort/filter/layout* only if columns change; keep it on for normal use.
- If `DataFolder` is wrong, every query errors; fix the parameter and refresh.
- A new, unknown rejection message type yields `UNCLASSIFIED` (and a REVIEW row in `tblChecks`), never a silent drop.

## 8. Investigation log

Short version: a separate typed table keyed on `finding_id`; helper formulas XLOOKUP into `tblFindings` to flag **NEW**, **DISAPPEARED** and **CHANGED**. Full design, columns, formulas and the refresh walkthrough are in `INVESTIGATION_LOG.md`.

## 9. Golden check (optional)

1. Set `SyntheticFixtureMode` to `true` (Home → Manage Parameters), load `ExpectedFindings` as `tblExpected`, refresh.
2. On `GoldenCheck`: `A2: =SORT(tblExpected[finding_id])` and `B2: =IF(ISNUMBER(MATCH($A$2#,tblFindings[finding_id],0)),"found","MISSING")`.
3. Reverse check: `D2: =FILTER(tblFindings[finding_id],ISNA(MATCH(tblFindings[finding_id],tblExpected[finding_id],0)),"none extra")`.
4. Compare classification: `C2: =XLOOKUP($A$2#,tblFindings[finding_id],tblFindings[evidence_class])=XLOOKUP($A$2#,tblExpected[finding_id],tblExpected[evidence_class])` (and the same for `counts_as_actionable`).
5. Expect 10 found, 0 missing, 0 extra, all TRUE. **Set the parameter back to `false` afterward.**

`ExpectedFindingsPath` must be the absolute path of `workbench\EXPECTED_FINDINGS.csv` (that file lives one level above `sample/`).

## 10. Not covered here

No macros, VBA, slicers, charts or refresh scheduling; add them only if needed. Constructing the real workbook is Step 6.
