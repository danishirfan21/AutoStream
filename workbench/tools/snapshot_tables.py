"""Write the six query-result tables as CSV files, computed by the Python reference detector.

These are the SNAPSHOT contents of the workbook tables (tblFindings, tblLatest, tblChecks, tblSourceRecords, tblRuns,
tblVehicles). They mirror what the Power Query scripts in queries/ are designed to produce; they are NOT produced by
Power Query. Usage:  python tools/snapshot_tables.py --out DIR [--synthetic-fixtures]
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import timezone
from pathlib import Path

WB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WB))
import reference_findings as rf  # noqa: E402

SOURCE_RECORD_COLUMNS = ["vin", "source_name", "source_record_id", "source_timestamp_utc", "payload_hash",
                         "raw_payload_json", "ts", "year", "make", "model", "trim", "mileage"]
LATEST_COLUMNS = ["key", "vin", "source_name", "record_count", "status", "latest_source_record_id", "latest_ts",
                  "year", "make", "model", "trim", "mileage"]
CHECK_COLUMNS = ["check", "observed", "expected", "status"]


def source_record_rows(source_rows: list[dict]) -> list[dict]:
    out = []
    for row in source_rows:
        r = rf.Rec(row)
        out.append({**{k: row[k] for k in SOURCE_RECORD_COLUMNS[:6]},
                    "ts": r.ts.astimezone(timezone.utc).isoformat() if r.ts else "",
                    "year": r.get("year") or "", "make": r.get("make") or "", "model": r.get("model") or "",
                    "trim": r.get("trim") or "", "mileage": "" if r.mileage() is None else r.mileage()})
    return out


def latest_rows(source_rows: list[dict]) -> list[dict]:
    recs = [rf.Rec(r) for r in source_rows]
    pairs = sorted({(r.vin, r.source) for r in recs})
    compared = list(rf.ATTRIBUTES) + ["mileage"]
    out = []
    for vin, source in pairs:
        pr = [r for r in recs if r.vin == vin and r.source == source]
        groups = rf.ts_groups(pr)
        last = groups[-1] if groups else None
        bad = rf.differing_fields(last, compared) if last else set()
        status = "UNORDERABLE_NO_TS" if groups is None else ("AMBIGUOUS_TIE" if bad else "OK")
        ok = status == "OK"

        def first(field):
            vals = [r.get(field) for r in last if r.get(field) is not None]
            return vals[0] if ok and vals else ""

        mil = [r.mileage() for r in last if r.mileage() is not None] if ok else []
        out.append({"key": f"{vin}|{source}", "vin": vin, "source_name": source, "record_count": len(pr),
                    "status": status, "latest_source_record_id": last[0].rid if ok else "",
                    "latest_ts": last[0].ts_text if ok else "", "year": first("year"), "make": first("make"),
                    "model": first("model"), "trim": first("trim"), "mileage": mil[0] if mil else ""})
    return out


def check_rows(source_rows: list[dict], error_rows: list[dict], findings: list[dict]) -> list[dict]:
    recs = [rf.Rec(r) for r in source_rows]
    ids = [f["finding_id"] for f in findings]
    rejected = [f for f in findings if f["issue_type"] == "REJECTED_RECORD"]
    occurrences = sum(int(f["occurrences_canonical_sequence"] or 0) for f in rejected)
    rows = [
        ("Source records with a timestamp that could not be parsed (ordering would treat them as missing)", 0,
         "0"),
        ("Source records with no source timestamp", sum(1 for r in recs if not r.ts_text),
         "0 expected in the sample (information otherwise)"),
        ("Accepted source records whose VIN is not 17 characters", sum(1 for r in recs if len(r.vin) != 17), "0"),
        ("Rejection occurrences in the log minus occurrences accounted for by REJECTED_RECORD findings",
         len(error_rows) - occurrences, "0"),
        ("Rejected records classified UNCLASSIFIED", sum(1 for f in rejected if f["rule_id"] == "UNCLASSIFIED"),
         "0 (otherwise map the new error type)"),
        ("Duplicate finding_id values", len(ids) - len(set(ids)), "0"),
        ("AMBIGUOUS_ORDER findings (records that cannot be ordered)",
         sum(1 for i in ids if i.startswith("AMBIGUOUS_ORDER|")), "0 expected in the sample"),
    ]
    return [{"check": c, "observed": o, "expected": e, "status": "PASS" if o == 0 else "REVIEW"} for c, o, e in rows]


def write(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--sample", type=Path, default=WB / "sample")
    ap.add_argument("--synthetic-fixtures", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    src, err = rf.load_sample(a.sample)
    findings = sorted(rf.detect(src, err, synthetic_fixture_mode=a.synthetic_fixtures),
                      key=lambda f: (f["issue_type"], f["finding_id"]))
    write(a.out / "findings.csv", rf.COLUMNS, findings)
    write(a.out / "latest.csv", LATEST_COLUMNS, latest_rows(src))
    write(a.out / "checks.csv", CHECK_COLUMNS, check_rows(src, err, findings))
    write(a.out / "source_records.csv", SOURCE_RECORD_COLUMNS, source_record_rows(src))
    for name in ("ingestion_runs", "vehicles"):
        rows = rf.read_csv(a.sample / f"{name}.csv")
        write(a.out / {"ingestion_runs": "runs.csv", "vehicles": "vehicles.csv"}[name], list(rows[0].keys()), rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
