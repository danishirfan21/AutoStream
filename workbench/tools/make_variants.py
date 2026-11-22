"""Create test copies of the sample folder for Step 6A (Excel runtime verification).

Usage:  python tools/make_variants.py --out <folder-outside-repo>

Each variant is a FULL COPY of workbench/sample with one change to source_records.csv, plus the answer the Python
reference detector gives for that copy (expected_real.csv = default mode, expected_synthetic.csv = synthetic mode).
Point the Excel DataFolder parameter at a variant folder, refresh, export Findings, and compare with
tools/compare_excel_findings.py. The committed sample is never modified. --out must not be inside the repository.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

WB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WB))
import reference_findings as rf  # noqa: E402

FORD, HONDA, TESLA = "1FTFW1E50PFA12345", "1HGCM82633A004352", "5YJ3E1EA7PF123456"


def _read(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames), list(r)


def _write(path: Path, header: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _pick(rows, vin, source, ts=None):
    hit = [r for r in rows if r["vin"] == vin and r["source_name"] == source and (ts is None or r["source_timestamp_utc"] == ts)]
    assert len(hit) == 1, (vin, source, ts, len(hit))
    return hit[0]


def _set_payload(row: dict, **kv) -> None:
    p = json.loads(row["raw_payload_json"])
    p.update(kv)
    row["raw_payload_json"] = json.dumps(p)
    row["payload_hash"] = hashlib.sha256(row["raw_payload_json"].encode()).hexdigest()


def v_baseline(rows):
    return rows


def v_tie_disagrees(rows):
    """Ford dealer gets a second record with the SAME timestamp but different mileage -> AMBIGUOUS_ORDER, no regression."""
    src = _pick(rows, FORD, "dealer_csv")
    dup = dict(src)
    _set_payload(dup, **{rf.SOURCES["dealer_csv"]["mileage"]: "99999"})
    return rows + [dup]


def v_tie_agrees(rows):
    """Same timestamp, identical values, different hash -> NOT ambiguous (nothing to disagree about)."""
    src = _pick(rows, FORD, "dealer_csv")
    dup = dict(src)
    dup["payload_hash"] = "duplicate-with-identical-values"
    return rows + [dup]


def v_missing_ts(rows):
    """Honda dealer: one of two records loses its source timestamp -> unorderable (NO_SOURCE_TIMESTAMP token)."""
    _pick(rows, HONDA, "dealer_csv", "2026-02-10T10:00:00Z")["source_timestamp_utc"] = ""
    return rows


def v_bad_mileage(rows):
    """Tesla later dealer record has non-numeric mileage: must stay visible, never coerced to a number."""
    row = _pick(rows, TESLA, "dealer_csv", "2026-02-10T10:00:00Z")
    _set_payload(row, **{rf.SOURCES["dealer_csv"]["mileage"]: "n/a"})
    return rows


def v_unparseable_ts(rows):
    """Tesla later dealer record has an unparseable timestamp text: Checks must show REVIEW."""
    _pick(rows, TESLA, "dealer_csv", "2026-02-10T10:00:00Z")["source_timestamp_utc"] = "not-a-date"
    return rows


def v_new_regression(rows):
    """Acceptance test: Tesla later dealer record drops from 9600 to 9000 miles -> one NEW MILEAGE_REGRESSION."""
    row = _pick(rows, TESLA, "dealer_csv", "2026-02-10T10:00:00Z")
    _set_payload(row, **{rf.SOURCES["dealer_csv"]["mileage"]: "9000"})
    return rows


VARIANTS = {
    "baseline": v_baseline,
    "new_regression": v_new_regression,
    "tie_disagrees": v_tie_disagrees,
    "tie_agrees": v_tie_agrees,
    "missing_ts": v_missing_ts,
    "bad_mileage": v_bad_mileage,
    "unparseable_ts": v_unparseable_ts,
}


def build(out: Path) -> list[str]:
    sample = WB / "sample"
    made = []
    for name, fn in VARIANTS.items():
        d = out / name
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(sample, d)
        header, rows = _read(d / "source_records.csv")
        rows = fn([dict(r) for r in rows])
        _write(d / "source_records.csv", header, rows)
        try:
            src, err = rf.load_sample(d)
            rf.detect(src, err)
        except ValueError as e:   # the Python oracle fails loudly on an unparseable timestamp; Power Query does not
            (d / "NO_EXPECTED_FILE.txt").write_text(chr(10).join([
                "The Python reference detector raises on this variant (" + str(e) + ").",
                "Power Query is designed to keep the record and treat the timestamp as missing.",
                "Expected in Excel (derived from the M design, NOT produced by an oracle):",
                "  - tblChecks row about a timestamp that could not be parsed = 1, status REVIEW",
                "  - tblFindings has an AMBIGUOUS_ORDER|<vin>|<source>|NO_SOURCE_TIMESTAMP row for that VIN",
                "  - no error anywhere in the query chain", ""]), encoding="utf-8")
            made.append(name)
            continue
        for mode, fname in ((False, "expected_real.csv"), (True, "expected_synthetic.csv")):
            found = rf.detect(src, err, synthetic_fixture_mode=mode)
            with (d / fname).open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=rf.COLUMNS, lineterminator="\n")
                w.writeheader()
                w.writerows(found)
        made.append(name)
    return made


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    out = a.out.resolve()
    if WB.parent in out.parents or out == WB.parent:
        print("--out must be outside the repository", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    for n in build(out):
        print("created", out / n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
