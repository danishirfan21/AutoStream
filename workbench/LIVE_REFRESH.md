# Going live: Power Query refresh for `AutoStream_DQ_Workbench.xlsx`

**Status (honest):** the six live queries are prepared (`queries/bundled/q*.pq`, generated from the 20 existing scripts by `tools/make_bundles.py`) and the workbook is wired to read its settings from a `Config` sheet. **The queries have never been executed.** The Excel on the build machine is unlicensed and cannot create or run Power Query, so connecting them is a one-time manual step in a licensed Microsoft 365 / Excel 2021+ desktop Excel (about 10 minutes). Until then the data tables are a snapshot from the Python detector (synthetic-fixture mode: 10 findings, 4 actionable). Do not describe refresh as working until you have run the acceptance test below.

## One-time connection

1. Open the workbook, enable editing, and look at the `Config` sheet: `DataFolderDefault` should show `<workbook folder>\sample`. (If the workbook sits on OneDrive/SharePoint, type a local folder in `DataFolderOverride`.) `SyntheticFixtureMode` stays `true`.
2. For each of the six queries `qSourceRecords, qLatest, qFindings, qChecks, qRuns, qVehicles`:
   ```powershell
   powershell -File workbench\tools\copy_query.ps1 qFindings
   ```
   Excel: **Data > Get Data > From Other Sources > Blank Query > Advanced Editor**, select all, paste, **Done**. Rename the query (Query Settings) to the same name, then **Home > Close & Load To… > Table > New worksheet**. If asked about privacy levels: *Ignore Privacy Levels* (Query Options).
3. **Repoint formulas.** Ctrl+H, *Options*, Within = *Workbook*, Look in = *Formulas*, Replace All, six times:
   `tblFindings[`→`qFindings[`, `tblLatest[`→`qLatest[`, `tblSourceRecords[`→`qSourceRecords[`, `tblChecks[`→`qChecks[`, `tblRuns[`→`qRuns[`, `tblVehicles[`→`qVehicles[`.
4. **Repoint pivots.** Click each of the first two PivotTables on `Pivots` > PivotTable Analyze > Change Data Source > `qFindings`. (The third reads `tblInvestigationLog`, which stays.)
5. Delete the six old snapshot sheets (`Findings, Checks, SourceRecords, Latest, Runs, Vehicles`) and rename the six new query sheets to those names. The `InvestigationLog`, `Reconcile`, `Scorecard` and `Pivots` sheets are kept as they are. (The colour rules on the old Findings sheet are not carried over; Reconcile, Scorecard and the log keep theirs.)
6. **Refresh settings** (what makes Refresh All safe for the pivots): for each of the six queries, Data > Queries & Connections > right-click > Properties > **untick "Enable background refresh"**. Then Data > **Refresh All** refreshes the queries first and the PivotTables after. Pivots also refresh on file open. If a pivot ever looks one step behind, press Refresh All a second time.

## Everyday workflow

Change the CSVs (or point `DataFolderOverride` at another folder) > **Data > Refresh All**. Findings are recomputed by the M scripts, and Reconcile, Scorecard and the PivotTables follow. The `InvestigationLog` is typed data in its own table, keyed by `finding_id`; refresh never writes to it. Its `change_flag` column shows `DISAPPEARED` for a logged finding that is no longer produced and `EVIDENCE CHANGED` when its values differ. New findings show blue italic on the Findings sheet until logged, and `InvestigationLog!P2` counts them.

## Acceptance test (run it once; record the result)

```powershell
python workbench\tools\make_variants.py --out <folder-outside-repo>\variants
```
`variants\new_regression` is a full copy of the sample where the Tesla's later dealer record drops from 9600 to 9000 miles. The Python detector says it should produce **11 findings, 5 actionable**, the one new finding being `MILEAGE_REGRESSION|5YJ3E1EA7PF123456|dealer_csv|5YJ3E1EA7PF123456|2026-02-10T10:00:00Z`.

1. Open the workbook; Scorecard shows 10 findings / 4 actionable. Type a status and note in one InvestigationLog row.
2. `Config > DataFolderOverride` = the `new_regression` folder path. **Refresh All.**
3. Expect: 11 findings, 5 actionable, mileage regressions +1, a Tesla finding on `Reconcile`, pivots updated, the new finding blue italic and `P2` +1, and your log note untouched.
4. Clear `DataFolderOverride`. **Refresh All.** Expect the original 10 / 4 and no new finding. Log rows still show `OK`.

If anything differs, compare the Findings table with `variants\new_regression\expected_synthetic.csv` (`tools/compare_excel_findings.py`). Fix actual errors in the `.pq` sources, then re-run `python tools/make_bundles.py` and repaste.
