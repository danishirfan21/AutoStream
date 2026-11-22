"""Compare detector output with the approved golden specification (EXPECTED_FINDINGS.csv).

Kept outside reference_findings.py so the detector stays independent of the golden file.
The golden file describes the SYNTHETIC fixture sample, so synthetic mode is requested explicitly here
(the detector's default is real-data classification).
Every column except finding_id (the key) and fixture_evidence (free-text narrative) is compared exactly.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

WB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WB))
import reference_findings as rf  # noqa: E402

PROSE = {"fixture_evidence"}
COMPARED = [c for c in rf.COLUMNS if c != "finding_id" and c not in PROSE]


def load_golden(path: Path = WB / "EXPECTED_FINDINGS.csv") -> dict[str, dict]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {r["finding_id"]: r for r in rows}


def compare(detected: list[dict], golden: dict[str, dict]) -> dict:
    det = {f["finding_id"]: f for f in detected}
    report = {"missing": sorted(set(golden) - set(det)), "extra": sorted(set(det) - set(golden)), "rows": {}}
    for fid in sorted(set(golden) & set(det)):
        diffs = {c: (golden[fid][c], det[fid][c]) for c in COMPARED if golden[fid][c] != det[fid][c]}
        report["rows"][fid] = diffs
    report["ok"] = not report["missing"] and not report["extra"] and not any(report["rows"].values())
    return report


def main() -> int:
    sample = WB / "sample"
    detected = rf.detect(*rf.load_sample(sample), synthetic_fixture_mode=True)
    golden = load_golden()
    rep = compare(detected, golden)
    for fid, diffs in rep["rows"].items():
        print(f"{'MATCH' if not diffs else 'DIFF '}  {len(COMPARED) - len(diffs)}/{len(COMPARED)} columns  {fid}")
        for c, (g, d) in diffs.items():
            print(f"        {c}: golden={g!r} detected={d!r}")
    for fid in rep["missing"]:
        print(f"MISSING  {fid}")
    for fid in rep["extra"]:
        print(f"EXTRA    {fid}")
    print(f"\ngolden={len(golden)} detected={len(detected)} compared_columns={len(COMPARED)} -> {'IDENTICAL' if rep['ok'] else 'DIFFERENT'}")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
