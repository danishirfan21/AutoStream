"""Reference data-quality detector: the verification oracle for the eventual Excel workbook.

Reads ONLY the extracted CSVs (source_records, ingestion_errors; price_observations is not needed because
mileage is read from the raw payload). Pure standard library. It never reads the approved expectations and
contains no expected finding, VIN or ID; everything is derived from the input rows.

Categories: MILEAGE_REGRESSION, ATTR_CONFLICT, ATTR_DRIFT, COVERAGE_GAP, REJECTED_RECORD, plus
AMBIGUOUS_ORDER (specified in the approved notes document; emitted instead of guessing).

Semantics (see the approved notes document):
  * Ordering uses the SOURCE-provided timestamp only. Row order, ingestion time, hashes and ids are never used.
  * Records of one scope sharing the greatest/compared timestamp but differing on a compared field are
    AMBIGUOUS: an AMBIGUOUS_ORDER finding is emitted and the affected comparison is skipped, never resolved.
  * A scope with 2+ records where any lacks a source timestamp cannot be ordered: AMBIGUOUS_ORDER with the
    timestamp token NO_SOURCE_TIMESTAMP. A scope with exactly one record lacking a timestamp is usable; it is
    flagged in the evidence text and its timestamp column is empty.
  * Findings are anomaly flags that warrant investigation. confirmed_pipeline_defect is always
    'none_demonstrated': nothing here demonstrates that AutoStream itself misbehaved.
  * REAL-DATA classification is the default (synthetic_fixture_mode=False): unexplained coverage gaps are
    COVERAGE_UNEXPLAINED (actionable) and rejected inputs are actionable. The demonstration-specific choices
    approved for the synthetic fixture sample (COVERAGE_FIXTURE_LIMITED gaps; deliberately rejected inputs not
    actionable) apply ONLY when synthetic_fixture_mode=True / the explicit --synthetic-fixtures flag is given.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

COLUMNS = ["finding_id", "issue_type", "rule_id", "evidence_class", "assessment", "confirmed_invalid_input",
           "confirmed_pipeline_defect", "counts_as_actionable", "vin", "field", "source_a", "source_record_id_a",
           "timestamp_a", "value_a", "source_b", "source_record_id_b", "timestamp_b", "value_b",
           "pipeline_error_type_evidence", "distinct_record_count", "occurrences_canonical_sequence",
           "explained_by_finding_id", "derived_from", "fixture_evidence"]

# The only place coupled to feed formats (mirrors backend/app/adapters.py field names).
SOURCES: dict[str, dict[str, str]] = {
    "dealer_csv": {"vin": "vin", "timestamp": "updated_at", "year": "year", "make": "make", "model": "model",
                   "trim": "trim", "mileage": "mileage", "price": "price", "record_key": "vin"},
    "marketplace_json": {"vin": "vehicle_vin", "timestamp": "updated", "year": "model_year", "make": "brand",
                         "model": "vehicle_model", "trim": "variant", "mileage": "odometer_miles",
                         "price": "asking_price", "record_key": "listing_id"},
}
ATTRIBUTES = ("year", "make", "model", "trim")  # compared for ATTR_CONFLICT / ATTR_DRIFT
NO_TS = "NO_SOURCE_TIMESTAMP"
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


# ---------------------------------------------------------------- loading
class Rec:
    __slots__ = ("vin", "source", "rid", "ts", "ts_text", "payload")

    def __init__(self, row: dict):
        if row["source_name"] not in SOURCES:
            raise ValueError(f"unknown source {row['source_name']!r}")
        self.vin, self.source, self.rid = row["vin"], row["source_name"], row["source_record_id"]
        self.ts_text = row["source_timestamp_utc"] or ""
        self.ts = datetime.fromisoformat(self.ts_text.replace("Z", "+00:00")) if self.ts_text else None
        self.payload = json.loads(row["raw_payload_json"])

    def get(self, logical: str) -> str | None:
        value = self.payload.get(SOURCES[self.source][logical])
        text = None if value is None else str(value).strip()
        return text or None

    def mileage(self) -> int | None:
        text = self.get("mileage")
        digits = re.sub(r"[^0-9-]", "", text) if text else ""
        return int(digits) if re.fullmatch(r"-?\d+", digits) else None


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_sample(sample_dir: Path) -> tuple[list[dict], list[dict]]:
    return read_csv(sample_dir / "source_records.csv"), read_csv(sample_dir / "ingestion_errors.csv")


def blank(**kw: str) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update(confirmed_pipeline_defect="none_demonstrated", **kw)
    return row


# ---------------------------------------------------------------- ordering helpers
def ts_groups(recs: list[Rec]) -> list[list[Rec]] | None:
    """Ascending groups of records sharing a source timestamp; None if ordering is impossible."""
    if len(recs) >= 2 and any(r.ts is None for r in recs):
        return None
    by_ts: dict[datetime | None, list[Rec]] = defaultdict(list)
    for r in recs:
        by_ts[r.ts].append(r)
    return [sorted(by_ts[k], key=lambda r: (r.source, r.rid)) for k in sorted(by_ts, key=lambda k: (k is None, k))]


def scope_of(recs: Iterable[Rec]) -> str:
    sources = {r.source for r in recs}
    return sources.pop() if len(sources) == 1 else "*"


class Ambiguities:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str, str], dict] = {}

    def add(self, vin: str, recs: list[Rec], ts_text: str, fields: Iterable[str]) -> None:
        key = (vin, scope_of(recs), ts_text or NO_TS)
        item = self.items.setdefault(key, {"fields": set(), "rids": set()})
        item["fields"].update(fields)
        item["rids"].update(f"{r.source}:{r.rid}" for r in recs)

    def findings(self) -> list[dict]:
        out = []
        for (vin, scope, ts), item in sorted(self.items.items()):
            fields = ",".join(sorted(item["fields"]))
            out.append(blank(
                finding_id=f"AMBIGUOUS_ORDER|{vin}|{scope}|{ts}", issue_type="AMBIGUOUS_ORDER",
                rule_id="TIMESTAMP_ORDER_UNAMBIGUOUS", evidence_class="ORDERING_AMBIGUITY",
                assessment="AMBIGUOUS_NOT_RESOLVED", confirmed_invalid_input="undetermined",
                counts_as_actionable="yes", vin=vin, field=fields, source_a=scope,
                timestamp_a="" if ts == NO_TS else ts, value_a="records=" + ";".join(sorted(item["rids"])),
                derived_from="FIXTURE_CONTENT",
                fixture_evidence=f"Records cannot be ordered by source timestamp for field(s) {fields}; no value was "
                                 "selected and dependent comparisons were skipped."))
        return out


def differing_fields(group: list[Rec], fields: Iterable[str]) -> set[str]:
    return {f for f in fields if len({r.get(f) for r in group if r.get(f) is not None}) > 1}


# ---------------------------------------------------------------- detectors
def mileage_regressions(by_vin: dict[str, list[Rec]], amb: Ambiguities) -> list[dict]:
    out = []
    for vin, recs in sorted(by_vin.items()):
        groups = ts_groups(recs)
        if groups is None:
            amb.add(vin, [r for r in recs if r.ts is None], "", ["mileage"])
            continue
        prev: tuple[Rec, int] | None = None
        for group in groups:
            if len({r.mileage() for r in group if r.mileage() is not None}) > 1:
                amb.add(vin, group, group[0].ts_text, ["mileage"])
                prev = None  # never compare across an unresolvable group
                continue
            values = [(r, r.mileage()) for r in group if r.mileage() is not None]
            if not values:
                continue
            cur, cur_m = values[0]
            if prev and cur_m < prev[1]:
                out.append(blank(
                    finding_id=f"MILEAGE_REGRESSION|{vin}|{cur.source}|{cur.rid}|{cur.ts_text}",
                    issue_type="MILEAGE_REGRESSION", rule_id="MILEAGE_NON_DECREASING",
                    evidence_class="SOURCE_DISCREPANCY", assessment="SUSPICIOUS_REQUIRES_INVESTIGATION",
                    confirmed_invalid_input="undetermined", counts_as_actionable="yes", vin=vin, field="mileage",
                    source_a=prev[0].source, source_record_id_a=prev[0].rid, timestamp_a=prev[0].ts_text,
                    value_a=str(prev[1]), source_b=cur.source, source_record_id_b=cur.rid,
                    timestamp_b=cur.ts_text, value_b=str(cur_m), derived_from="FIXTURE_CONTENT",
                    fixture_evidence=f"Mileage decreased {prev[1]} -> {cur_m} between consecutive observations "
                                     f"ordered by source timestamp ({prev[0].ts_text} -> {cur.ts_text}). Anomaly "
                                     "flag only; not proof of corruption."))
            prev = (cur, cur_m)
    return out


def attribute_findings(by_vin: dict[str, list[Rec]], amb: Ambiguities) -> tuple[list[dict], list[dict]]:
    conflicts, drifts = [], []
    for vin, recs in sorted(by_vin.items()):
        # --- latest record per source (ATTR_CONFLICT)
        latest: dict[str, dict[str, tuple[Rec, bool]]] = {}
        for source in sorted({r.source for r in recs}):
            src_recs = [r for r in recs if r.source == source]
            groups = ts_groups(src_recs)
            if groups is None:
                amb.add(vin, [r for r in src_recs if r.ts is None], "", ATTRIBUTES)
                continue
            last = groups[-1]
            bad = differing_fields(last, ATTRIBUTES)
            if bad:
                amb.add(vin, last, last[0].ts_text, bad)
            for f in ATTRIBUTES:
                if f not in bad:
                    rec = next((r for r in last if r.get(f) is not None), None)
                    if rec:
                        latest.setdefault(f, {})[source] = (rec, len(src_recs) == 1 and rec.ts is None)
        for f in ATTRIBUTES:
            sources = sorted(latest.get(f, {}))
            for i, sa in enumerate(sources):
                for sb in sources[i + 1:]:
                    (a, a_flag), (b, b_flag) = latest[f][sa], latest[f][sb]
                    if a.get(f) != b.get(f):
                        note = " A source timestamp is missing on a single record (flagged)." if a_flag or b_flag else ""
                        conflicts.append(blank(
                            finding_id=f"ATTR_CONFLICT|{vin}|{f}|{sa}~{sb}", issue_type="ATTR_CONFLICT",
                            rule_id="ATTR_CROSS_SOURCE_AGREEMENT", evidence_class="SOURCE_DISCREPANCY",
                            assessment="SUSPICIOUS_REQUIRES_INVESTIGATION", confirmed_invalid_input="undetermined",
                            counts_as_actionable="yes", vin=vin, field=f, source_a=sa, source_record_id_a=a.rid,
                            timestamp_a=a.ts_text, value_a=a.get(f) or "", source_b=sb, source_record_id_b=b.rid,
                            timestamp_b=b.ts_text, value_b=b.get(f) or "", derived_from="FIXTURE_CONTENT",
                            fixture_evidence=f"Latest record per source by source timestamp disagrees on {f}: "
                                             f"{a.get(f)} vs {b.get(f)}.{note}"))
        # --- versions of one source record (ATTR_DRIFT)
        for source, rid in sorted({(r.source, r.rid) for r in recs}):
            versions = [r for r in recs if (r.source, r.rid) == (source, rid)]
            groups = ts_groups(versions)
            if groups is None:
                amb.add(vin, versions, "", ATTRIBUTES)
                continue
            for f in ATTRIBUTES:
                bad = [g for g in groups if len({r.get(f) for r in g if r.get(f) is not None}) > 1]
                if bad:
                    for g in bad:
                        amb.add(vin, g, g[0].ts_text, [f])
                    continue
                known = [(g[0], next(r.get(f) for r in g if r.get(f) is not None)) for g in groups
                         if any(r.get(f) is not None for r in g)]
                for (ra, va), (rb, vb) in zip(known, known[1:]):
                    if va != vb:
                        drifts.append(blank(
                            finding_id=f"ATTR_DRIFT|{vin}|{f}|{source}|{rb.ts_text}", issue_type="ATTR_DRIFT",
                            rule_id="ATTR_SAME_SOURCE_STABILITY", evidence_class="SOURCE_DISCREPANCY",
                            assessment="OBSERVED_CHANGE_UNVERIFIED", confirmed_invalid_input="undetermined",
                            counts_as_actionable="yes", vin=vin, field=f, source_a=source, source_record_id_a=rid,
                            timestamp_a=ra.ts_text, value_a=va, source_b=source, source_record_id_b=rid,
                            timestamp_b=rb.ts_text, value_b=vb, derived_from="FIXTURE_CONTENT",
                            fixture_evidence=f"Same source record changed {f}: {va} -> {vb} "
                                             f"({ra.ts_text} -> {rb.ts_text}). May be a correction; cause unknown."))
    return conflicts, drifts


# -------- rejected records
def classify_rule(error_type: str, message: str) -> str:
    """Map a stored pipeline error to a semantic rule. Fragile by nature (type + message shape); never guesses."""
    if error_type == "InvalidOperation":
        return "PRICE_NUMERIC"  # only parse_price raises decimal errors in the pipeline
    if error_type == "ValidationError":
        header = re.match(r"^(\d+) validation errors? for ", message)
        fields = re.findall(r"^([A-Za-z_][\w.]*)$", message, re.M)
        if header and header.group(1) == "1" and fields == ["vin"]:
            return "VIN_FORMAT"
    return "UNCLASSIFIED"


def violates(rule: str, source: str, payload: dict) -> bool | None:
    """Independent check from the payload that the stated rule is really violated (None = cannot say)."""
    cfg = SOURCES.get(source)
    if not cfg:
        return None
    if rule == "VIN_FORMAT":
        return not VIN_RE.fullmatch(str(payload.get(cfg["vin"], "")).strip().upper())
    if rule == "PRICE_NUMERIC":
        text = re.sub(r"[\s$,]", "", str(payload.get(cfg["price"], "")))
        return not re.fullmatch(r"\d+(\.\d+)?", text)
    return None


def rejected_findings(errors: list[dict], synthetic: bool) -> list[dict]:
    groups: dict[str, dict] = {}
    for e in errors:
        source, payload = e["run_source_name"], json.loads(e["raw_payload_json"])
        cfg = SOURCES.get(source, {})
        rule = classify_rule(e["error_type"], e["error_message"])
        key = str(payload.get(cfg.get("record_key", ""), "")).strip() or e["stored_source_record_id"]
        ts = str(payload.get(cfg.get("timestamp", ""), "") or "") or NO_TS
        fid = f"REJECTED_RECORD|{source}|{key}|{rule}|{ts}"
        g = groups.setdefault(fid, {"e": [], "payloads": set(), "types": set(), "source": source, "payload": payload,
                                    "rule": rule, "ts": ts, "key": key, "stored": e["stored_source_record_id"]})
        g["e"].append(e)
        g["payloads"].add(json.dumps(payload, sort_keys=True))
        g["types"].add(e["error_type"])
    out = []
    for fid, g in sorted(groups.items()):
        cfg, rule, p = SOURCES.get(g["source"], {}), g["rule"], g["payload"]
        fld = {"VIN_FORMAT": cfg.get("vin", ""), "PRICE_NUMERIC": cfg.get("price", "")}.get(rule, "")
        confirmed = "yes" if violates(rule, g["source"], p) else "undetermined"
        out.append(blank(
            finding_id=fid, issue_type="REJECTED_RECORD", rule_id=rule, evidence_class="REJECTED_INPUT",
            assessment="EXPECTED_REJECTION", confirmed_invalid_input=confirmed,
            counts_as_actionable="no" if synthetic else "yes",
            vin=str(p.get(cfg.get("vin", ""), "")), field=fld, source_a=g["source"],
            source_record_id_a=g["stored"], timestamp_a="" if g["ts"] == NO_TS else g["ts"],
            value_a=f"{fld}={p.get(fld, '')}" if fld else "", pipeline_error_type_evidence=";".join(sorted(g["types"])),
            distinct_record_count=str(len(g["payloads"])), occurrences_canonical_sequence=str(len(g["e"])),
            derived_from="FIXTURE_CONTENT+PIPELINE_BEHAVIOR",
            fixture_evidence=f"{len(g['e'])} rejection occurrence(s) of {len(g['payloads'])} distinct payload(s) "
                             f"for rule {rule}; stored record id {g['stored']}."))
    return out


def coverage_findings(recs: list[Rec], rejected: list[dict], errors: list[dict], synthetic: bool) -> list[dict]:
    sources = sorted({r.source for r in recs} | {e["run_source_name"] for e in errors if e["run_source_name"] in SOURCES})
    out = []
    for vin in sorted({r.vin for r in recs}):
        present = sorted({r.source for r in recs if r.vin == vin})
        for missing in (s for s in sources if s not in present):
            sa = present[0]
            ra = max((r for r in recs if r.vin == vin and r.source == sa), key=lambda r: (r.ts_text, r.rid))
            expl = [f["finding_id"] for f in rejected if f["source_a"] == missing and f["vin"].strip().upper() == vin]
            if expl:
                cls, why = "COVERAGE_EXPLAINED", "A rejected record exists for this VIN in the missing source."
            elif synthetic:
                cls, why = "COVERAGE_FIXTURE_LIMITED", ("OBSERVATION CAUSED BY LIMITED SYNTHETIC FIXTURES; NOT A "
                                                        "SOURCE DEFECT. Excluded from actionable defect counts.")
            else:
                cls, why = "COVERAGE_UNEXPLAINED", "No record and no rejected record in the missing source."
            out.append(blank(
                finding_id=f"COVERAGE_GAP|{vin}|missing:{missing}", issue_type="COVERAGE_GAP", rule_id="SOURCE_COVERAGE",
                evidence_class=cls, assessment="COVERAGE_OBSERVATION", confirmed_invalid_input="not_applicable",
                counts_as_actionable="yes" if cls == "COVERAGE_UNEXPLAINED" else "no", vin=vin, field="source_presence",
                source_a=sa, source_record_id_a=ra.rid, timestamp_a=ra.ts_text, value_a="present", source_b=missing,
                value_b="absent", explained_by_finding_id=expl[0] if expl else "",
                derived_from="FIXTURE_CONTENT+PIPELINE_BEHAVIOR" if expl else "FIXTURE_CONTENT",
                fixture_evidence=f"VIN present in {sa} accepted records, absent from {missing}. {why}"))
    return out


# ---------------------------------------------------------------- entry points
def detect(source_rows: list[dict], error_rows: list[dict], synthetic_fixture_mode: bool = False) -> list[dict]:
    recs = [Rec(r) for r in source_rows]
    by_vin: dict[str, list[Rec]] = defaultdict(list)
    for r in recs:
        by_vin[r.vin].append(r)
    amb = Ambiguities()
    mileage = mileage_regressions(by_vin, amb)
    conflicts, drifts = attribute_findings(by_vin, amb)
    rejected = rejected_findings(error_rows, synthetic_fixture_mode)
    coverage = coverage_findings(recs, rejected, error_rows, synthetic_fixture_mode)
    findings = mileage + conflicts + drifts + rejected + coverage + amb.findings()
    ids = [f["finding_id"] for f in findings]
    assert len(ids) == len(set(ids)), "finding ids must be unique"
    return sorted(findings, key=lambda f: (f["issue_type"], f["finding_id"]))


def write_csv(findings: list[dict], out) -> None:
    w = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(findings)


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect findings from extracted sample CSVs.")
    ap.add_argument("--sample", type=Path, default=Path(__file__).resolve().parent / "sample")
    ap.add_argument("--out", type=Path, help="write CSV here (default: stdout)")
    ap.add_argument("--synthetic-fixtures", action="store_true",
                    help="apply the synthetic-fixture classifications (default: real-data classification)")
    a = ap.parse_args()
    findings = detect(*load_sample(a.sample), synthetic_fixture_mode=a.synthetic_fixtures)
    if a.out:
        with a.out.open("w", encoding="utf-8", newline="") as f:
            write_csv(findings, f)
    else:
        write_csv(findings, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
