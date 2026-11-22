"""Compare the Findings table exported from Excel with an expected CSV (Step 6A).

Usage:
  python tools/compare_excel_findings.py EXPORT.csv                       # vs EXPECTED_FINDINGS.csv (needs SyntheticFixtureMode=true in Excel)
  python tools/compare_excel_findings.py EXPORT.csv --expected X.csv      # vs any expected file (e.g. a variant's expected_real.csv)
  python tools/compare_excel_findings.py EXPORT.csv --data-folder DIR --mode real|synthetic
                                                                          # vs the Python detector run on that folder

All columns except fixture_evidence (free-text narrative) are compared exactly, plus the header order.
Exit code 0 = identical, 1 = differences, 2 = usage/format problem. Nothing is written.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

WB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WB))
sys.path.insert(0, str(WB / "tools"))
import golden_compare as gc  # noqa: E402
import reference_findings as rf  # noqa: E402


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8-sig", newline="") as f:   # Excel "CSV UTF-8" writes a BOM
        r = csv.DictReader(f)
        header = list(r.fieldnames or [])
        return header, list(r)


def compare_export(export_header, export_rows, expected_rows) -> dict:
    problems = []
    if export_header != rf.COLUMNS:
        problems.append(f"header differs: expected {rf.COLUMNS}, got {export_header}")
    ids = [r["finding_id"] for r in export_rows]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        problems.append(f"duplicate finding_id in export: {dup}")
    expected = {r["finding_id"]: r for r in expected_rows}
    if problems:
        return {"ok": False, "problems": problems, "missing": [], "extra": [], "rows": {}}
    rep = gc.compare(export_rows, expected)
    rep["problems"] = problems
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("export", type=Path)
    ap.add_argument("--expected", type=Path)
    ap.add_argument("--data-folder", type=Path)
    ap.add_argument("--mode", choices=["real", "synthetic"], default="real")
    a = ap.parse_args()
    try:
        header, rows = read_csv(a.export)
        if a.data_folder:
            src, err = rf.load_sample(a.data_folder)
            expected_rows = rf.detect(src, err, synthetic_fixture_mode=(a.mode == "synthetic"))
            label = f"detector on {a.data_folder} ({a.mode})"
        else:
            exp = a.expected or (WB / "EXPECTED_FINDINGS.csv")
            expected_rows = read_csv(exp)[1]
            label = str(exp)
    except (OSError, KeyError) as e:
        print(f"cannot read input: {e!r}", file=sys.stderr)
        return 2
    rep = compare_export(header, rows, expected_rows)
    for p in rep["problems"]:
        print("PROBLEM ", p)
    for fid, diffs in rep["rows"].items():
        print(f"{'MATCH' if not diffs else 'DIFF '}  {fid}")
        for c, (g, d) in diffs.items():
            print(f"        {c}: expected={g!r} excel={d!r}")
    for fid in rep["missing"]:
        print(f"MISSING  {fid}")
    for fid in rep["extra"]:
        print(f"EXTRA    {fid}")
    print(f"\nexpected from {label}\nexcel_rows={len(rows)} -> {'IDENTICAL' if rep['ok'] else 'DIFFERENT'}")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
