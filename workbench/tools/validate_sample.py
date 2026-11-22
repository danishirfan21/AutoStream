"""Validate workbench/sample/ (stdlib only). Usage: validate_sample.py [--sample DIR] [--compare DIR]

Checks: static read-only SQL, file/column/row integrity, payload-hash recomputation, provenance against the
repo fixtures, traceability of EVERY approved golden finding to extracted rows, and (with --compare) that
another independently generated sample is byte-identical.

This is a traceability check, not detection: it looks up the exact evidence each golden row cites; it does
not discover findings.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

WB = Path(__file__).resolve().parents[1]
FIXTURES = WB.parent / "fixtures"

HEADERS = {
    "vehicles": ["vin", "year", "make", "model", "trim"],
    "source_records": ["vin", "source_name", "source_record_id", "source_timestamp_utc", "payload_hash", "raw_payload_json"],
    "price_observations": ["vin", "source_name", "observed_at_utc", "price", "mileage", "location", "matching_source_records"],
    "ingestion_runs": ["run_seq", "source_name", "status", "total_records", "inserted_records", "updated_records",
                       "duplicate_records", "invalid_records", "failed_records", "error_message"],
    "ingestion_errors": ["run_seq", "run_source_name", "occurrence_in_run", "stored_source_record_id", "error_type",
                         "error_message", "raw_payload_json"],
    "ingestion_steps": ["step", "fixture_file", "fixture_sha256", "note"],
}
EXPECTED_ROWS = {"vehicles": 5, "source_records": 9, "price_observations": 9, "ingestion_runs": 6,
                 "ingestion_errors": 4, "ingestion_steps": 6}
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
VIN_RE = re.compile(r"^[A-Z0-9]{17}$")
# payload field names per source (adapters.py)
FIELDS = {"dealer_csv": {"vin": "vin", "timestamp": "updated_at", "trim": "trim", "mileage": "mileage"},
          "marketplace_json": {"vin": "vehicle_vin", "timestamp": "updated", "trim": "variant", "mileage": "odometer_miles"}}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    return ok


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def payload_hash(payload: dict) -> str:  # mirrors backend/app/ingestion.py payload_hash
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def fixture_rows() -> list[dict]:
    rows = []
    for name in ("dealer_feed_v1.csv", "dealer_feed_v2.csv", "invalid_feed.csv"):
        rows += read(FIXTURES / name)
    rows += json.loads((FIXTURES / "marketplace_feed.json").read_text(encoding="utf-8"))
    return rows


def validate(sample: Path) -> None:
    # 0. static read-only guard on the SQL
    bad = [f.name for f in (WB / "sql").glob("*.sql")
           if re.search(r"\b(insert|update|delete|truncate|drop|alter|create|grant|revoke|copy)\b",
                        "\n".join(l.split("--")[0] for l in f.read_text(encoding="utf-8").splitlines()), re.I)]
    check("SQL files contain no write/DDL keywords", not bad, ", ".join(bad))

    # 1. files, headers, ragged rows, row counts
    t: dict[str, list[dict]] = {}
    for name, header in HEADERS.items():
        path = sample / f"{name}.csv"
        if not check(f"{name}.csv exists", path.is_file()):
            return
        raw = list(csv.reader(path.open(encoding="utf-8", newline="")))
        check(f"{name}: header exact", raw[0] == header, str(raw[0]))
        check(f"{name}: no ragged rows", all(len(r) == len(header) for r in raw[1:]))
        check(f"{name}: no CR bytes (LF only)", b"\r" not in path.read_bytes())
        t[name] = read(path)
        check(f"{name}: {EXPECTED_ROWS[name]} rows", len(t[name]) == EXPECTED_ROWS[name], f"got {len(t[name])}")
    sums = dict(l.split("  ", 1)[::-1] for l in (sample / "SHA256SUMS").read_text().splitlines())
    check("SHA256SUMS matches files", set(sums) == {f"{n}.csv" for n in HEADERS}
          and all(hashlib.sha256((sample / n).read_bytes()).hexdigest() == h for n, h in sums.items()))

    # 2. column integrity
    sr, ob, er, runs, veh = t["source_records"], t["price_observations"], t["ingestion_errors"], t["ingestion_runs"], t["vehicles"]
    check("vehicles: VINs are 17 chars, unique", all(VIN_RE.match(v["vin"]) for v in veh) and len({v["vin"] for v in veh}) == len(veh))
    check("source_records: VIN, source, record id non-empty", all(r["vin"] and r["source_name"] and r["source_record_id"] for r in sr))
    check("source_records: source timestamps well-formed", all(TS_RE.match(r["source_timestamp_utc"]) for r in sr))
    check("source_records: unique (source, record id, payload hash)",
          len({(r["source_name"], r["source_record_id"], r["payload_hash"]) for r in sr}) == len(sr))
    check("source_records: payload_hash recomputes from raw_payload_json",
          all(payload_hash(json.loads(r["raw_payload_json"])) == r["payload_hash"] for r in sr))
    check("source_records: VIN column equals payload VIN",
          all(json.loads(r["raw_payload_json"])[FIELDS[r["source_name"]]["vin"]].strip().upper() == r["vin"] for r in sr))
    check("source_records: timestamp column equals payload timestamp",
          all(json.loads(r["raw_payload_json"])[FIELDS[r["source_name"]]["timestamp"]] == r["source_timestamp_utc"] for r in sr))
    check("price_observations: timestamps well-formed, each links to exactly 1 source record",
          all(TS_RE.match(o["observed_at_utc"]) and o["matching_source_records"] == "1" for o in ob))
    check("price_observations: each links back to an existing source record",
          all(any(r["vin"] == o["vin"] and r["source_name"] == o["source_name"] and r["source_timestamp_utc"] == o["observed_at_utc"]
                  for r in sr) for o in ob))
    check("ingestion_errors: raw payloads are valid JSON objects", all(isinstance(json.loads(e["raw_payload_json"]), dict) for e in er))
    check("ingestion_runs: run_seq is 1..6 in order", [r["run_seq"] for r in runs] == [str(i) for i in range(1, 7)])

    # 3. canonical sequence and run counts
    steps = t["ingestion_steps"]
    check("steps: source adapter per run matches fixture kind",
          [r["source_name"] for r in runs] == ["dealer_csv"] * 4 + ["marketplace_json"] * 2)
    check("steps: fixture hashes equal current fixture files",
          all(s["fixture_sha256"] == hashlib.sha256((FIXTURES / s["fixture_file"]).read_bytes()).hexdigest() for s in steps))
    check("runs: replays (2, 6) inserted nothing and duplicated all accepted rows",
          runs[1]["inserted_records"] == "0" and runs[1]["duplicate_records"] == "3"
          and runs[5]["inserted_records"] == "0" and runs[5]["duplicate_records"] == "3")
    check("runs: invalid counts 0,0,0,2,1,1", [r["invalid_records"] for r in runs] == ["0", "0", "0", "2", "1", "1"])
    check("runs: invalid_records per run equals error rows per run",
          all(int(r["invalid_records"]) == sum(1 for e in er if e["run_seq"] == r["run_seq"]) for r in runs))

    # 4. provenance: every payload is an unmodified fixture row
    fx = fixture_rows()
    check("provenance: every source-record payload equals a fixture row", all(json.loads(r["raw_payload_json"]) in fx for r in sr))
    check("provenance: every rejected payload equals a fixture row", all(json.loads(e["raw_payload_json"]) in fx for e in er))

    # 5. golden traceability
    golden = read(WB / "EXPECTED_FINDINGS.csv")
    occ = read(WB / "EXPECTED_REJECTION_OCCURRENCES.csv")
    check("golden: 10 findings, 4 actionable", len(golden) == 10 and sum(g["counts_as_actionable"] == "yes" for g in golden) == 4)
    rejected = [g for g in golden if g["issue_type"] == "REJECTED_RECORD"]
    check("golden: 3 distinct rejected records vs 4 extracted occurrences", len(rejected) == 3 and len(er) == 4 and len(occ) == 4)

    def record(vin: str, src: str, ts: str) -> dict | None:
        m = [r for r in sr if r["vin"] == vin and r["source_name"] == src and r["source_timestamp_utc"] == ts]
        return m[0] if len(m) == 1 else None

    def observation(vin: str, src: str, ts: str) -> dict | None:
        m = [o for o in ob if o["vin"] == vin and o["source_name"] == src and o["observed_at_utc"] == ts]
        return m[0] if len(m) == 1 else None

    for g in golden:
        fid, typ, vin = g["finding_id"], g["issue_type"], g["vin"]
        sa, sb = g["source_a"], g["source_b"]
        ok, why = True, ""
        if typ == "MILEAGE_REGRESSION":
            for s, rid, ts, val in ((sa, g["source_record_id_a"], g["timestamp_a"], g["value_a"]),
                                    (sb, g["source_record_id_b"], g["timestamp_b"], g["value_b"])):
                rec, o = record(vin, s, ts), observation(vin, s, ts)
                ok &= bool(rec and o and rec["source_record_id"] == rid and o["mileage"] == val)
        elif typ in ("ATTR_CONFLICT", "ATTR_DRIFT"):
            for s, rid, ts, val in ((sa, g["source_record_id_a"], g["timestamp_a"], g["value_a"]),
                                    (sb, g["source_record_id_b"], g["timestamp_b"], g["value_b"])):
                rec = record(vin, s, ts)
                ok &= bool(rec and rec["source_record_id"] == rid and json.loads(rec["raw_payload_json"])[FIELDS[s]["trim"]] == val)
        elif typ == "REJECTED_RECORD":
            rows = [e for e in er if e["stored_source_record_id"] == g["source_record_id_a"] and e["run_source_name"] == sa]
            payloads = {e["raw_payload_json"] for e in rows}
            f = FIELDS[sa]
            p = json.loads(next(iter(payloads))) if len(payloads) == 1 else {}
            ok = (len(rows) == int(g["occurrences_canonical_sequence"]) and len(payloads) == 1
                  and all(e["error_type"] == g["pipeline_error_type_evidence"] for e in rows)
                  and p.get(f["timestamp"]) == g["timestamp_a"] and p.get(f["vin"], "").strip().upper() == vin)
            why = f"{len(rows)} occurrence(s), {len(payloads)} distinct payload(s)"
        elif typ == "COVERAGE_GAP":
            present = [r for r in sr if r["vin"] == vin and r["source_name"] == sa]
            absent = [r for r in sr if r["vin"] == vin and r["source_name"] == sb]
            ok = bool(present) and not absent
            if g["explained_by_finding_id"]:
                rej = next(x for x in rejected if x["finding_id"] == g["explained_by_finding_id"])
                ok &= any(e["stored_source_record_id"] == rej["source_record_id_a"] and e["run_source_name"] == sb for e in er)
        check(f"golden traceable: {fid}", bool(ok), why)

    # occurrence file vs extracted occurrences (1:1 on step + stored record id + error type)
    occ_keys = Counter((o["ingestion_step"], o["pipeline_source_record_id"], o["pipeline_error_type_evidence"]) for o in occ)
    er_keys = Counter((e["run_seq"], e["stored_source_record_id"], e["error_type"]) for e in er)
    check("golden occurrences file == extracted ingestion_errors (step, record id, error type)", occ_keys == er_keys)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=Path, default=WB / "sample")
    ap.add_argument("--compare", type=Path, help="independently generated sample that must be byte-identical")
    a = ap.parse_args()
    validate(a.sample)
    if a.compare:
        names = sorted(p.name for p in a.sample.iterdir())
        same = names == sorted(p.name for p in a.compare.iterdir()) and all(
            (a.sample / n).read_bytes() == (a.compare / n).read_bytes() for n in names)
        check(f"determinism: {a.compare} is byte-identical ({len(names)} files)", same)
    width = max(len(n) for n, _, _ in results)
    for n, ok, d in results:
        print(f"{'PASS' if ok else 'FAIL'}  {n.ljust(width)}  {d if not ok or d else ''}".rstrip())
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
