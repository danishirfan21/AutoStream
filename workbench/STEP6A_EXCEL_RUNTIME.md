# Step 6A: Excel runtime verification (you run this; nothing below has been executed)

**Honest status.** The M scripts have only been checked by static tests. No result in this file was produced by Excel. Every "expected" value below comes from the Python reference detector or from reading the sample CSVs, not from Power Query. **You must run the steps in Excel and tell me the outcome; I will not mark anything as passed until you do.**

You need desktop Excel for Windows (Microsoft 365). You do not need a database or any AutoStream process. Total effort: about 45 minutes. Step 6B (the real workbook) is **not** started.

## What 6A needs (minimum subset of `WORKBOOK_GUIDE.md`)

Only sections 1 (create queries) and 9 (golden check) matter now. Sheets, `XLOOKUP` reconciliation, scorecard, pivots, conditional formatting and the log are Step 6B. You create **13 queries**, all *connection-only* except two, and one scratch workbook.

| # | Query | Load as |
|---|---|---|
| 1 | `DataFolder` | parameter |
| 2 | `SyntheticFixtureMode` | parameter |
| 3 | `SourceMap` | connection only |
| 4 | `Lib` | connection only |
| 5 | `Raw_SourceRecords` | table (checkpoint 1) |
| 6 | `Raw_IngestionErrors` | table (checkpoint 1) |
| 7 | `SourceRecords` | table (checkpoint 2) |
| 8 | `F_Mileage` | connection only |
| 9 | `F_AttributeFindings` | connection only |
| 10 | `F_Rejected` | table (checkpoint 3) |
| 11 | `F_Coverage` | table (checkpoint 3) |
| 12 | `F_Ambiguous` | table (checkpoint 3) |
| 13 | `Findings` | table `tblFindings` (checkpoint 4) |

Later in 6A (optional): `VinSourceLatest`, `Checks`.

`F_Mileage` and `F_AttributeFindings` return **records** (`[Findings = ..., Candidates = ...]`), so Excel cannot load them as a table. Keep them connection-only; you inspect them through `Findings`.

## Prepare

Use a **scratch workbook outside the repository**, e.g. `<scratch>\dq_6a.xlsx` (do not save it under `workbench/`).

Make the test variants (copies of the sample with one change each, plus the Python-computed answer):

```powershell
python workbench\tools\make_variants.py --out <scratch>\variants
```

Helper to copy a query to the clipboard (optional, saves opening files):

```powershell
workbench\tools\copy_query.ps1 -List
```

```powershell
workbench\tools\copy_query.ps1 -Next
```

(`-Next` copies the next query in the right order; `-Reset` starts over.) If PowerShell blocks scripts, run it as `powershell -ExecutionPolicy Bypass -File ...`.

## Step A: Create the parameters

1. New workbook → **Data → Get Data → Launch Power Query Editor**.
2. **Home → New Source → Other Sources → Blank Query**. **View → Advanced Editor**. Select all, paste the text of `queries\DataFolder.pq`, **Done**. In the right-hand *Query Settings* pane rename it to `DataFolder`.
3. Edit the pasted text value to your path, for example `workbench\sample` (no trailing `\`). Easiest: **Home → Manage Parameters → Edit** (if it appears there) and set *Current Value*; otherwise open the Advanced Editor and replace the placeholder text.
   - **Check A1:** the query shows as a parameter (icon with a "ab" box / listed under Parameters). If it appears as a plain query, that is also fine; it is a text value query. Tell me which.
4. Same for `SyntheticFixtureMode` (leave `false`).

## Step B: Raw loaders (Checkpoint 1)

Paste in order: `SourceMap`, `Lib`, `Raw_SourceRecords`, `Raw_IngestionErrors`.

| Check | Expected | Why it matters |
|---|---|---|
| B1 `Raw_SourceRecords` loads, no error banner | 9 rows, 6 columns: `vin, source_name, source_record_id, source_timestamp_utc, payload_hash, raw_payload_json` | CSV parsing, `QuoteStyle.Csv` with embedded commas/quotes |
| B2 | All columns type "ABC" (text) | no silent coercion |
| B3 `Raw_IngestionErrors` | 4 rows, 7 columns (`run_seq … raw_payload_json`); error messages keep multi-line text | embedded newlines handled |
| B4 `Lib` and `SourceMap` | each shows a single Record | they are helper records, not tables |

If B1 or B3 fails, copy the **full error message and the failing step name**.

## Step C: Normalization (Checkpoint 2)

Paste `SourceRecords`. Expected 9 rows. Column `vin` is text 17 characters, `ts` is a date/time/timezone. Expected values:

| vin (last 4) | source | `source_timestamp_utc` text | year | make | model | trim | mileage |
|---|---|---|---|---|---|---|---|
| 2345 | dealer_csv | 2026-01-10T10:00:00Z | 2023 | Ford | F-150 | XLT | 18300 |
| 2345 | marketplace_json | 2026-08-01T10:45:00Z | 2023 | Ford | F-150 | XLT | 18100 |
| 4352 | dealer_csv | 2026-01-10T10:00:00Z | 2023 | Honda | Accord | EX | 12400 |
| 4352 | dealer_csv | 2026-02-10T10:00:00Z | 2023 | Honda | Accord | EX | 12800 |
| 4352 | marketplace_json | 2026-08-01T10:30:00Z | 2023 | Honda | Accord | EX-L | 12100 |
| 3456 (Altima, 1N4…) | marketplace_json | 2026-08-01T11:00:00Z | 2018 | Nissan | Altima | S | 45200 |
| 3456 (Fusion, 3FA…) | dealer_csv | 2026-02-10T10:00:00Z | 2017 | Ford | Fusion | SE | 71200 |
| 3456 (Tesla, 5YJ…) | dealer_csv | 2026-01-10T10:00:00Z | 2023 | Tesla | Model 3 | Long Range | 9600 |
| 3456 (Tesla, 5YJ…) | dealer_csv | 2026-02-10T10:00:00Z | 2023 | Tesla | Model 3 | Long Range AWD | 9600 |

Specific risks to confirm (tell me yes/no for each):
- C1 No error cells anywhere (red `Error`). If a row shows `Error` in `payload`/`ts`, click it and copy the message.
- C2 `ts` for `...Z` strings is a valid datetimezone (not null). Hover a value: `2026-01-10 10:00:00 +00:00` (or similar).
- C3 `raw_payload_json` is unchanged and `payload_hash` equals the CSV value.
- C4 The Tesla pair shares mileage 9600 and differs only in trim (this is the drift case).

## Step D: Finding queries (Checkpoint 3)

Paste, in this order: `F_Mileage`, `F_AttributeFindings`, `F_Rejected`, `F_Coverage`, `F_Ambiguous`. After each, confirm no error banner.

Expected: `F_Rejected` 3 rows, `F_Coverage` 3 rows, `F_Ambiguous` 0 rows (header only). For `F_Mileage`/`F_AttributeFindings` click the cell of the record field `Findings`/`Conflicts`/`Drifts` (use the right-click → *Add as new query* if you wish): expected 2 mileage regressions, 1 conflict, 1 drift.

Risk to confirm: **D1** `F_Ambiguous` returns a table with 0 rows and the right columns rather than an error (empty-range handling).

## Step E: Findings output vs the 10 golden findings (Checkpoint 4)

1. Paste `Findings`. Expected 10 rows × 24 columns, no error.
2. **Close & Load To… → Table** for `Findings` only (and for the raw/Checkpoint tables if you want to look at them). Rename the sheet table to `tblFindings`.
3. Export it: select the sheet with `tblFindings` → **File → Save As → CSV UTF-8 (Comma delimited)** → `<scratch>\export_synth.csv`. (Excel will warn that only the active sheet is saved; accept. Then continue to work in the `.xlsx`; save it again under its own name if you want to keep it.)
4. Compare. The first run, with `SyntheticFixtureMode = true`, matches the **golden file**:

   First set `SyntheticFixtureMode` to `true` (Manage Parameters → Current Value → `true`; or edit the query text) and **Refresh** `Findings`, export as above.

```powershell
python workbench\tools\compare_excel_findings.py <scratch>\export_synth.csv
```

   Expected output ends with `-> IDENTICAL` (10 rows, every column except the `fixture_evidence` prose).

5. Set `SyntheticFixtureMode` back to `false`, refresh, export to `export_real.csv`:

```powershell
python workbench\tools\compare_excel_findings.py <scratch>\export_real.csv --data-folder workbench\sample --mode real
```

   Expected `IDENTICAL` (9 actionable, 10 findings; only the classification of 5 rows differs from the golden).

If the output says DIFFERENT, send me the whole output. The tool prints each differing column as `expected=... excel=...`; no changes are made by the tool.

Also eyeball the following in Excel (these are not fully visible in the comparison):
- E1 `vin` keeps leading characters and all 17 characters (no scientific notation or trimming).
- E2 `timestamp_a/b` show the original `…Z` source text, not an Excel date serial.
- E3 `distinct_record_count` = 1 on each of the 3 REJECTED_RECORD rows; `occurrences_canonical_sequence` sum = 4.
- E4 `mk-invalid` row has 2 occurrences (the same payload logged twice), still one finding.

## Step F: Variant tests (duplicate handling, ambiguous ordering)

For each variant below: set the `DataFolder` value to `<scratch>\variants\<name>`, **Refresh** `Findings`, export as `<scratch>\export_<name>.csv`, and run the compare tool with the variant's own expected file:

```powershell
python workbench\tools\compare_excel_findings.py <scratch>\export_tie_disagrees.csv --expected <scratch>\variants\tie_disagrees\expected_real.csv
```

| Variant | Change | Expected result (from the Python detector) |
|---|---|---|
| `baseline` | none | same 10 as the real-data run |
| `tie_agrees` | Ford dealer gets a duplicate record: same timestamp, identical values | no new finding; ids equal baseline |
| `tie_disagrees` | Ford dealer gets a duplicate with the same timestamp but mileage 99999 | `AMBIGUOUS_ORDER|1FTFW1E50PFA12345|dealer_csv|2026-01-10T10:00:00Z` appears; the Ford mileage regression disappears |
| `missing_ts` | Honda dealer's later record has no timestamp | `AMBIGUOUS_ORDER|1HGCM82633A004352|dealer_csv|NO_SOURCE_TIMESTAMP`; the Honda regression and the trim conflict disappear |
| `bad_mileage` | Tesla later record mileage `n/a` | ids equal baseline (visible, not coerced; does not crash). Check the mileage-less record in `SourceRecords` shows null mileage and the original payload still holds `n/a` |
| `unparseable_ts` | Tesla later record timestamp text `not-a-date` | No oracle file: the Python detector raises. Expect no Excel error; a `Checks` REVIEW row and an `AMBIGUOUS_ORDER|…|NO_SOURCE_TIMESTAMP` for the Tesla VIN. Report what you actually see. |

`tie_disagrees`/`missing_ts` exercise the chronological-comparison and ambiguity rules the user approved: Excel should never pick one of two tied records arbitrarily.

After the last variant, **set `DataFolder` back to the real sample folder**.

## Step G: Refresh All reliability

1. With everything loaded (including the `Findings` table and, if you want, a PivotTable on `tblFindings`), press **Data → Refresh All** once. Note: does it finish without error? Do the tables keep 10 rows?
2. Change `DataFolder` to `variants\tie_disagrees`, press **Refresh All once**, and check `Findings` shows the new ids without a second refresh.
3. Hold a stopwatch: tell me roughly how long a full refresh takes (expected: a few seconds).
4. If you create a PivotTable on `tblFindings` (Insert → PivotTable → From Table), change the data folder and press Refresh All once: does the PivotTable update straight away? (Step 6B decision: whether we need *Refresh All twice* or *refresh on open*.)
5. Query Options: check **Data → Queries & Connections → right-click query → Properties → "Refresh this connection on Refresh All"** is ticked; **uncheck "Enable background refresh"** if results look half-updated. Tell me which you needed.

## Optional: Checks and VinSourceLatest

Paste `VinSourceLatest` (expected 7 rows: one per VIN/source pair; Honda/dealer latest = `2026-02-10T10:00:00Z`) and `Checks` (7 rows, all `PASS` on the real sample; `observed` = 0 on each). Load as `tblLatest`/`tblChecks`.

## What to send back

1. For each checkpoint (A, B1–B4, C1–C4, D1, E1–E4, F variants, G1–G5): **pass / fail / not tried**.
2. For any fail: the **exact error text, the query name and the failing step name** (the grey step under *Applied Steps* with an ⚠).
3. The three `compare_excel_findings.py` outputs (synthetic, real, and each variant) pasted in full.
4. Excel build (File → Account → About Excel) and whether `LET`, `XLOOKUP`, `FILTER` work (try `=XLOOKUP(1,{1},{2})`).
5. Whether any "formula firewall", "privacy levels" or "DataFormat.Error" dialog appeared and what you chose.

## What I will do with the results (after you report)

Fix any M execution failure in `workbench/queries/` (keeping the static tests passing and re-checking variants against the Python oracle), update this file with the **observed** results, and only then start Step 6B. I will not claim any runtime success that you have not reported.

## Prepared and tested vs. yours to run

| Prepared by me, tested here (Python only) | Yours to run in Excel (untested) |
|---|---|
| `tools/make_variants.py`: variants and oracle answers; sample untouched; tested | Pasting and running every query |
| `tools/compare_excel_findings.py`: detects missing/extra/changed rows, header/duplicate problems, BOM/CRLF; tested | Whether the M parses and evaluates |
| `tools/copy_query.ps1`: clipboard helper; `-List` and single-name copy executed once, `-Next` not exercised | All results in Steps B–G |
| `tests/test_step6a_tools.py` (6 tests) | Refresh All behavior |
