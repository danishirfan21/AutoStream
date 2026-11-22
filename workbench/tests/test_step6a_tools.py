"""Tests for the Step 6A helpers (variant generator and Excel-export comparer). Never touch the committed sample."""
from __future__ import annotations

import csv
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

import reference_findings as rf

WB = Path(__file__).resolve().parents[1]
TOOLS = WB / "tools"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)


@pytest.fixture(scope="module")
def variants(tmp_path_factory):
    out = tmp_path_factory.mktemp("variants")
    before = {p.name: sha(p) for p in (WB / "sample").iterdir()}
    r = run(TOOLS / "make_variants.py", "--out", out)
    assert r.returncode == 0, r.stderr
    assert {p.name: sha(p) for p in (WB / "sample").iterdir()} == before   # committed sample untouched
    return out


def write_rows(path: Path, rows, header=rf.COLUMNS, bom=False):
    with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)


def test_refuses_output_inside_repo():
    assert run(TOOLS / "make_variants.py", "--out", WB / "_x").returncode == 2


def test_baseline_variant_equals_sample(variants):
    assert sha(variants / "baseline" / "source_records.csv") == sha(WB / "sample" / "source_records.csv")


def test_variant_expectations_are_the_intended_scenarios(variants):
    def ids(name):
        return {r["finding_id"] for r in csv.DictReader((variants / name / "expected_real.csv").open(encoding="utf-8"))}
    base = ids("baseline")
    ford_reg = "MILEAGE_REGRESSION|1FTFW1E50PFA12345|marketplace_json|mk-1002|2026-08-01T10:45:00Z"
    assert ids("tie_agrees") == base
    assert ids("bad_mileage") == base
    assert ford_reg in base and ford_reg not in ids("tie_disagrees")
    assert "AMBIGUOUS_ORDER|1FTFW1E50PFA12345|dealer_csv|2026-01-10T10:00:00Z" in ids("tie_disagrees")
    assert "AMBIGUOUS_ORDER|1HGCM82633A004352|dealer_csv|NO_SOURCE_TIMESTAMP" in ids("missing_ts")
    assert (variants / "unparseable_ts" / "NO_EXPECTED_FILE.txt").exists()


def test_compare_accepts_identical_export_even_with_excel_bom_and_crlf(variants, tmp_path):
    exp = variants / "baseline" / "expected_real.csv"
    rows = list(csv.DictReader(exp.open(encoding="utf-8")))
    ex = tmp_path / "export.csv"
    write_rows(ex, rows, bom=True)
    r = run(TOOLS / "compare_excel_findings.py", ex, "--expected", exp)
    assert r.returncode == 0 and "IDENTICAL" in r.stdout, r.stdout


def test_compare_flags_every_kind_of_difference(variants, tmp_path):
    exp = variants / "baseline" / "expected_real.csv"
    rows = list(csv.DictReader(exp.open(encoding="utf-8")))
    ex = tmp_path / "export.csv"

    changed = [dict(r) for r in rows]
    changed[0]["counts_as_actionable"] = "no"
    write_rows(ex, changed)
    r = run(TOOLS / "compare_excel_findings.py", ex, "--expected", exp)
    assert r.returncode == 1 and "counts_as_actionable" in r.stdout

    write_rows(ex, rows[1:])
    r = run(TOOLS / "compare_excel_findings.py", ex, "--expected", exp)
    assert r.returncode == 1 and "MISSING" in r.stdout

    write_rows(ex, rows + [dict(rows[0], finding_id="X|extra")])
    r = run(TOOLS / "compare_excel_findings.py", ex, "--expected", exp)
    assert r.returncode == 1 and "EXTRA" in r.stdout

    write_rows(ex, rows + [rows[0]])
    r = run(TOOLS / "compare_excel_findings.py", ex, "--expected", exp)
    assert r.returncode == 1 and "duplicate" in r.stdout

    write_rows(ex, rows, header=list(reversed(rf.COLUMNS)))
    r = run(TOOLS / "compare_excel_findings.py", ex, "--expected", exp)
    assert r.returncode == 1 and "header" in r.stdout


def test_compare_against_golden_and_against_detector(tmp_path):
    golden = list(csv.DictReader((WB / "EXPECTED_FINDINGS.csv").open(encoding="utf-8")))
    ex = tmp_path / "export.csv"
    write_rows(ex, golden)
    assert run(TOOLS / "compare_excel_findings.py", ex).returncode == 0
    r = run(TOOLS / "compare_excel_findings.py", ex, "--data-folder", WB / "sample", "--mode", "real")
    assert r.returncode == 1   # golden is the synthetic classification, so real-mode must differ
    assert run(TOOLS / "compare_excel_findings.py", ex, "--data-folder", WB / "sample", "--mode", "synthetic").returncode == 0
