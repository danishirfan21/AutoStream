# Refresh-safe investigation log

**Status:** design and formulas only; not yet built or run in Excel (see `VERIFICATION_CHECKLIST.md`, V-10 to V-13).

## Principle

The log is an ordinary Excel Table (`tblInvestigationLog`) on its own sheet, typed by the analyst. **No Power Query writes to it, and no query reads from it.** A refresh replaces `tblFindings` but cannot touch the log. The two are joined only by the text key `finding_id`.

`finding_id` is stable because it is built from the evidence, never from a database-generated value: e.g. `MILEAGE_REGRESSION|1HGCM82633A004352|marketplace_json|mk-1001|2026-08-01T10:30:00Z` (VIN, source, source record id, source timestamp). The same underlying observation produces the same id on every refresh and every machine. Row position and sort order are irrelevant.

## Columns of `tblInvestigationLog`

| Column | Typed or formula | Notes |
|---|---|---|
| `finding_id` | typed (pasted) | **Key.** Paste as *values* (Paste Special → Values). Never retype. |
| `status` | typed, data-validation list | `Open`, `In progress`, `Needs source info`, `Closed - no issue`, `Closed - data issue`, `Closed - system issue`, `Won't fix` |
| `owner` | typed | |
| `opened_on` | typed | date, not `TODAY()` |
| `last_updated` | typed | date |
| `notes` | typed | what was checked and what was concluded. Do not state a root cause unless you verified it. |
| `issue_type_at_logging` | typed (pasted value) | snapshot |
| `evidence_snapshot` | typed (pasted value) | snapshot of `value_a` / `value_b` at logging time, e.g. `EX | EX-L` |
| `in_current_run` | formula | see below |
| `evidence_now` | formula | |
| `change_flag` | formula | `OK` / `DISAPPEARED` / `EVIDENCE CHANGED` |

Typed columns come first; the three formula columns come last. Pivot 3 (status counts) reads `status` and `issue_type_at_logging` directly.

## How to log a finding

1. On `Findings`, copy the `finding_id` cell (single cell, no filter hidden rows involved).
2. On `InvestigationLog`, in the first empty row, **Paste Special → Values** into `finding_id`.
3. Paste `issue_type` into `issue_type_at_logging` (as values).
4. In `evidence_snapshot` type or paste `value_a | value_b` (as values).
5. Set `status` = `Open`, owner and date. Add notes as you work.

Data validation on `status`: Data → Data Validation → List → source = the status values above (type them comma-separated). Duplicate keys are caught by the `duplicate_key` helper column below, not by data validation.

## Helper formulas (entered once in row 1 of the column; Excel auto-fills the table)

`in_current_run` (does this finding still exist?):

```
=IF(ISNUMBER(MATCH([@[finding_id]],tblFindings[finding_id],0)),"yes","NO")
```

`evidence_now` (current evidence text; empty when it disappeared):

```
=IFERROR(XLOOKUP([@[finding_id]],tblFindings[finding_id],tblFindings[value_a]&" | "&tblFindings[value_b]),"")
```

`change_flag`:

```
=IF([@[in_current_run]]="NO","DISAPPEARED",
 IF([@[evidence_snapshot]]="","OK",
 IF([@[evidence_snapshot]]=[@[evidence_now]],"OK","EVIDENCE CHANGED")))
```

`duplicate_key` (optional, catches double entries):

```
=IF(COUNTIF([finding_id],[@[finding_id]])>1,"DUPLICATE","")
```

Spaces and case: the key is compared exactly; do not let Excel auto-trim or auto-correct. If a paste adds a trailing space, `in_current_run` becomes `NO` (this is the intended loud failure).

## What "changed" and "disappeared" mean

| Situation | What you see | Meaning | Action |
|---|---|---|---|
| Same id, same values | `OK` | Finding still true | Continue |
| Same id, different `value_a`/`value_b` | `EVIDENCE CHANGED` | Because the id contains the identifying keys but not the values, the same observation now shows different values (e.g. a re-extract changed the stored payload) | Re-read the evidence; update `evidence_snapshot` after review |
| Id absent from `tblFindings` | `DISAPPEARED` | The data no longer produces this finding. Either the source records changed/were corrected, or the id components changed (e.g. a newer record means the "later timestamp" in the id moved), or `SyntheticFixtureMode` was switched, or `DataFolder` points at a different extract | Do **not** delete the row. Set status, add a note ("closed because corrected in source" is a conclusion only if verified) |
| Id in `tblFindings` but not in the log | listed by the triage spill (below) | New finding, not yet triaged | Log it |

A deliberate consequence: when new evidence appears (for example a third mileage reading with a new timestamp), the old finding may disappear and a **new** id appears. The old log row is kept and shows `DISAPPEARED`; the new finding appears in triage. This is visible, not hidden.

Not detectable by id: two different real-world problems that happen to share an id. The id design makes that unlikely; check `evidence_snapshot` when in doubt.

## Triage spill: findings not yet logged

On `Findings` or a `Triage` sheet:

```
=FILTER(tblFindings[finding_id],ISNA(MATCH(tblFindings[finding_id],tblInvestigationLog[finding_id],0)),"all findings logged")
```

Add a second spill beside it for context: `=XLOOKUP(A2#,tblFindings[finding_id],tblFindings[issue_type])`.

To show only actionable ones: add `*(tblFindings[counts_as_actionable]="yes")` to the include argument, i.e. `FILTER(tblFindings[finding_id],ISNA(MATCH(...))*(tblFindings[counts_as_actionable]="yes"),"none")`.

## Conditional formatting on the log

- `change_flag` = `DISAPPEARED` → grey fill, bold.
- `change_flag` = `EVIDENCE CHANGED` → amber fill.
- `duplicate_key` = `DUPLICATE` → red.
- `status` begins with `Closed` → grey text.

## Refresh walkthrough (what to expect)

1. **Before:** log has 2 rows (`ATTR_CONFLICT|1HGCM…|trim|dealer_csv~marketplace_json` Open, and a Tesla drift row).
2. **Refresh with the same CSV files:** both rows `OK`; triage lists the other 8 findings.
3. **Edit a copy of `source_records.csv`** (never the committed one; make a second folder and repoint `DataFolder`) so the Honda marketplace and dealer latest trims agree (change one payload's trim): the conflict row now shows `DISAPPEARED`.
4. Point `DataFolder` back; both rows `OK` again. No log data changed at any point.

## Backing up the log

The log is typed work. Before changing `DataFolder` or structural changes, save a copy of the workbook. The log is not stored in the repository and is not re-generated.
