"""Independent tests for reference_findings.py. The committed sample and golden files are never modified:
every mutation works on in-memory copies."""
from __future__ import annotations

import copy
import json
import random
import re
from pathlib import Path

import pytest

import golden_compare as gc
import reference_findings as rf

WB = Path(__file__).resolve().parents[1]
SAMPLE = WB / "sample"
HONDA, FORD, TESLA = "1HGCM82633A004352", "1FTFW1E50PFA12345", "5YJ3E1EA7PF123456"
TS_DEALER_1, TS_DEALER_2, TS_MKT = "2026-01-10T10:00:00Z", "2026-02-10T10:00:00Z", "2026-08-01T10:30:00Z"
MKT_REJECT = "REJECTED_RECORD|marketplace_json|mk-invalid|VIN_FORMAT|2026-08-01T11:15:00Z"


def detect(source_rows, error_rows):
    """Detector in the explicit synthetic-fixture mode that the golden file describes."""
    return rf.detect(source_rows, error_rows, synthetic_fixture_mode=True)


@pytest.fixture(scope="module")
def sample():
    return rf.load_sample(SAMPLE)


@pytest.fixture
def data(sample):
    return copy.deepcopy(sample[0]), copy.deepcopy(sample[1])


def ids(findings, issue_type=None):
    return {f["finding_id"] for f in findings if issue_type is None or f["issue_type"] == issue_type}


def by_id(findings):
    return {f["finding_id"]: f for f in findings}


def edit(rows, vin=None, source=None, ts=None, rid=None, **payload):
    """Change payload fields of exactly one source record; returns that row."""
    hit = [r for r in rows if (vin is None or r["vin"] == vin) and (source is None or r["source_name"] == source)
           and (ts is None or r["source_timestamp_utc"] == ts) and (rid is None or r["source_record_id"] == rid)]
    assert len(hit) == 1, f"selector matched {len(hit)} rows"
    row = hit[0]
    p = json.loads(row["raw_payload_json"])
    p.update(payload)
    row["raw_payload_json"] = json.dumps(p)
    return row


def set_ts(row, new_ts):
    key = rf.SOURCES[row["source_name"]]["timestamp"]
    p = json.loads(row["raw_payload_json"])
    p[key] = new_ts
    row["raw_payload_json"] = json.dumps(p)
    row["source_timestamp_utc"] = new_ts


def rec(vin, source, rid, ts, **fields):
    """Synthetic source-record row using logical field names (year, make, model, trim, mileage)."""
    cfg = rf.SOURCES[source]
    payload = {cfg["vin"]: vin, cfg["timestamp"]: ts}
    if cfg["record_key"] != "vin":
        payload[cfg["record_key"]] = rid
    payload.update({cfg[k]: v for k, v in fields.items()})
    return {"vin": vin, "source_name": source, "source_record_id": rid, "source_timestamp_utc": ts or "",
            "payload_hash": "x", "raw_payload_json": json.dumps(payload)}


# ------------------------------------------------------------------ independence
def test_detector_contains_no_hardcoded_findings():
    src = (WB / "reference_findings.py").read_text(encoding="utf-8")
    assert "EXPECTED_FINDINGS" not in src and "golden" not in src.lower()
    assert not re.findall(r"[A-HJ-NPR-Z0-9]{17}", src), "no VIN literal may appear in the detector"
    assert not [fid for fid in gc.load_golden() if fid in src]


def test_detector_reads_only_the_two_sample_csvs_it_needs():
    src = (WB / "reference_findings.py").read_text(encoding="utf-8")
    assert set(re.findall(r'"(\w+\.csv)"', src)) == {"source_records.csv", "ingestion_errors.csv"}


# ------------------------------------------------------------------ golden comparison
def test_matches_golden_on_every_compared_column(sample):
    report = gc.compare(detect(*sample), gc.load_golden())
    assert report["missing"] == [] and report["extra"] == []
    assert all(not d for d in report["rows"].values()), report["rows"]
    assert len(report["rows"]) == 10 and len(gc.COMPARED) == 22


def test_counts_and_flags(sample):
    f = detect(*sample)
    assert len(f) == 10
    assert sum(x["counts_as_actionable"] == "yes" for x in f) == 4
    assert {x["confirmed_pipeline_defect"] for x in f} == {"none_demonstrated"}
    rej = [x for x in f if x["issue_type"] == "REJECTED_RECORD"]
    assert len(rej) == 3 and sum(int(x["occurrences_canonical_sequence"]) for x in rej) == 4
    assert all(x["distinct_record_count"] == "1" for x in rej)
    assert not ids(f, "AMBIGUOUS_ORDER")


def test_no_exception_names_or_database_ids_in_finding_ids(sample):
    for fid in ids(detect(*sample)):
        assert "ValidationError" not in fid and "InvalidOperation" not in fid
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", fid)


def test_mileage_read_from_payload_agrees_with_extracted_observations(sample):
    obs = rf.read_csv(SAMPLE / "price_observations.csv")
    for r in sample[0]:
        o = [x for x in obs if x["vin"] == r["vin"] and x["source_name"] == r["source_name"]
             and x["observed_at_utc"] == r["source_timestamp_utc"]]
        assert len(o) == 1 and int(o[0]["mileage"]) == rf.Rec(r).mileage()


# ------------------------------------------------------------------ determinism / identity independence
def test_row_order_and_database_values_do_not_change_results(sample):
    base = detect(*sample)
    sr, er = copy.deepcopy(sample[0]), copy.deepcopy(sample[1])
    random.Random(7).shuffle(sr)
    random.Random(8).shuffle(er)
    for r in sr:
        r["payload_hash"] = "0" * 64          # hashes are never used
    for e in er:
        e["occurrence_in_run"] = "99"         # run/occurrence numbering is evidence only
    assert detect(sr, er) == base
    assert detect(*sample) == base


def test_input_rows_are_not_mutated(sample):
    before = copy.deepcopy(sample)
    detect(*sample)
    assert sample == before


# ------------------------------------------------------------------ negative tests: values
def test_raising_mileage_removes_only_that_regression(data):
    sr, er = data
    edit(sr, HONDA, "marketplace_json", odometer_miles=12900)
    f = detect(sr, er)
    assert not [x for x in ids(f, "MILEAGE_REGRESSION") if HONDA in x]
    assert any(FORD in x for x in ids(f, "MILEAGE_REGRESSION"))
    assert len(f) == 9


def test_lowering_mileage_creates_a_new_regression(data):
    sr, er = data
    edit(sr, TESLA, "dealer_csv", TS_DEALER_2, mileage="9000")
    f = by_id(detect(sr, er))
    fid = f"MILEAGE_REGRESSION|{TESLA}|dealer_csv|{TESLA}|{TS_DEALER_2}"
    assert fid in f and (f[fid]["value_a"], f[fid]["value_b"]) == ("9600", "9000")
    assert len(f) == 11


def test_changing_trim_values_removes_conflict_and_drift(data):
    sr, er = data
    edit(sr, HONDA, "marketplace_json", variant="EX")              # now agrees with dealer
    edit(sr, TESLA, "dealer_csv", TS_DEALER_2, trim="Long Range")   # now stable
    f = detect(sr, er)
    assert not ids(f, "ATTR_CONFLICT") and not ids(f, "ATTR_DRIFT")
    assert len(f) == 8


def test_conflict_uses_the_latest_dealer_record(sample):
    sr, er = copy.deepcopy(sample[0]), copy.deepcopy(sample[1])
    edit(sr, HONDA, "dealer_csv", TS_DEALER_2, trim="EX-L")        # latest dealer value now matches marketplace
    f = detect(sr, er)
    assert not ids(f, "ATTR_CONFLICT")
    assert any(HONDA in x for x in ids(f, "ATTR_DRIFT"))           # EX -> EX-L between dealer versions

    sr2 = copy.deepcopy(sample[0])
    edit(sr2, HONDA, "dealer_csv", TS_DEALER_1, trim="EX-L")        # only an OLDER dealer value changed
    f2 = detect(sr2, er)
    assert any(HONDA in x for x in ids(f2, "ATTR_CONFLICT"))        # latest dealer is still EX -> conflict stays
    assert any(HONDA in x for x in ids(f2, "ATTR_DRIFT"))           # and v1 -> v2 now drifts


# ------------------------------------------------------------------ negative tests: timestamps
def test_timestamp_change_reorders_mileage_chronologically(data):
    sr, er = data
    set_ts(edit(sr, HONDA, "marketplace_json", rid="mk-1001"), "2026-01-20T10:00:00Z")  # between dealer v1 and v2
    f = by_id(detect(sr, er))
    old = f"MILEAGE_REGRESSION|{HONDA}|marketplace_json|mk-1001|{TS_MKT}"
    new = f"MILEAGE_REGRESSION|{HONDA}|marketplace_json|mk-1001|2026-01-20T10:00:00Z"
    assert old not in f and new in f
    assert (f[new]["value_a"], f[new]["value_b"]) == ("12400", "12100")
    assert f"ATTR_CONFLICT|{HONDA}|trim|dealer_csv~marketplace_json" in f     # dealer's Feb record is still latest


def test_row_order_cannot_substitute_for_timestamps(data):
    sr, er = data
    honda = sorted((r for r in sr if r["vin"] == HONDA), key=lambda r: r["source_timestamp_utc"], reverse=True)
    others = [r for r in sr if r["vin"] != HONDA]
    assert ids(detect(honda + others, er)) == ids(detect(sr, er))


def test_a_changed_timestamp_is_a_different_drift_finding(data):
    sr, er = data
    set_ts(edit(sr, TESLA, "dealer_csv", TS_DEALER_2), "2026-03-01T10:00:00Z")
    f = ids(detect(sr, er))
    assert f"ATTR_DRIFT|{TESLA}|trim|dealer_csv|2026-03-01T10:00:00Z" in f
    assert f"ATTR_DRIFT|{TESLA}|trim|dealer_csv|{TS_DEALER_2}" not in f


# ------------------------------------------------------------------ negative tests: source identity
def test_record_id_is_part_of_mileage_ids(data):
    sr, er = data
    edit(sr, HONDA, "marketplace_json", listing_id="mk-9999")["source_record_id"] = "mk-9999"
    f = ids(detect(sr, er), "MILEAGE_REGRESSION")
    assert f"MILEAGE_REGRESSION|{HONDA}|marketplace_json|mk-9999|{TS_MKT}" in f
    assert f"MILEAGE_REGRESSION|{HONDA}|marketplace_json|mk-1001|{TS_MKT}" not in f


def test_different_record_id_is_a_different_record_not_a_drift(data):
    sr, er = data
    edit(sr, TESLA, "dealer_csv", TS_DEALER_2)["source_record_id"] = "OTHER"
    assert not [x for x in ids(detect(sr, er), "ATTR_DRIFT") if TESLA in x]


def test_adding_a_record_from_the_missing_source_closes_a_coverage_gap(data):
    sr, er = data
    sr.append(rec(TESLA, "marketplace_json", "mk-2001", "2026-08-02T09:00:00Z", year="2023", make="Tesla",
                  model="Model 3", trim="Long Range AWD", mileage="9700"))
    f = detect(sr, er)
    assert f"COVERAGE_GAP|{TESLA}|missing:marketplace_json" not in ids(f)
    assert len(ids(f, "COVERAGE_GAP")) == 2


def test_newest_listing_of_a_source_drives_the_conflict(data):
    sr, er = data
    sr.append(rec(HONDA, "marketplace_json", "mk-3000", "2026-09-01T00:00:00Z", year="2023", make="Honda",
                  model="Accord", trim="Touring", mileage="13000"))
    f = by_id(detect(sr, er))
    key = f"ATTR_CONFLICT|{HONDA}|trim|dealer_csv~marketplace_json"
    assert f[key]["source_record_id_b"] == "mk-3000" and f[key]["value_b"] == "Touring"


# ------------------------------------------------------------------ negative tests: rejection occurrences
def test_dropping_a_replay_occurrence_keeps_one_id_and_lowers_the_count(data):
    sr, er = data
    f = by_id(detect(sr, [e for e in er if e["run_seq"] != "6"]))
    assert (f[MKT_REJECT]["occurrences_canonical_sequence"], f[MKT_REJECT]["distinct_record_count"]) == ("1", "1")
    assert len(ids(f.values(), "REJECTED_RECORD")) == 3


def test_extra_replay_adds_occurrences_not_findings(data):
    sr, er = data
    extra = copy.deepcopy([e for e in er if e["run_seq"] == "6"][0])
    extra["run_seq"] = "7"
    f = by_id(detect(sr, er + [extra]))
    assert f[MKT_REJECT]["occurrences_canonical_sequence"] == "3" and len(f) == 10


def test_changed_payload_timestamp_is_a_new_distinct_rejected_record(data):
    sr, er = data
    e = [x for x in er if x["run_seq"] == "6"][0]
    p = json.loads(e["raw_payload_json"])
    p["updated"] = "2026-09-09T00:00:00Z"
    e["raw_payload_json"] = json.dumps(p)
    rej = ids(detect(sr, er), "REJECTED_RECORD")
    assert len(rej) == 4 and "REJECTED_RECORD|marketplace_json|mk-invalid|VIN_FORMAT|2026-09-09T00:00:00Z" in rej


def test_positional_stored_id_does_not_change_the_finding_id(sample):
    er2 = [dict(e, stored_source_record_id="row-7" if e["stored_source_record_id"] == "row-4" else e["stored_source_record_id"])
           for e in sample[1]]
    f = by_id(detect(sample[0], er2))
    assert ids(f.values()) == ids(detect(*sample))
    assert f[MKT_REJECT]["source_record_id_a"] == "row-7"           # evidence follows the data, the ID does not


def test_unrecognised_error_is_unclassified_not_guessed(data):
    sr, er = data
    for e in er:
        if e["error_type"] == "InvalidOperation":
            e["error_type"] = "SomethingNew"
    f = by_id(detect(sr, er))
    fid = "REJECTED_RECORD|dealer_csv|1N4AL3AP9JC123456|UNCLASSIFIED|2026-01-10T10:00:00Z"
    assert fid in f and f[fid]["confirmed_invalid_input"] == "undetermined" and f[fid]["field"] == ""
    assert f["COVERAGE_GAP|1N4AL3AP9JC123456|missing:dealer_csv"]["explained_by_finding_id"] == fid


def test_a_rule_claim_is_checked_against_the_payload(data):
    sr, er = data
    for e in er:
        if e["error_type"] == "InvalidOperation":
            p = json.loads(e["raw_payload_json"])
            p["price"] = "12000"
            e["raw_payload_json"] = json.dumps(p)
    f = by_id(detect(sr, er))
    fid = "REJECTED_RECORD|dealer_csv|1N4AL3AP9JC123456|PRICE_NUMERIC|2026-01-10T10:00:00Z"
    assert f[fid]["confirmed_invalid_input"] == "undetermined"      # price is numeric, so the claim is not confirmed


def test_missing_payload_timestamp_uses_the_token(data):
    sr, er = data
    e = [x for x in er if x["run_seq"] == "5"][0]
    p = json.loads(e["raw_payload_json"])
    del p["updated"]
    e["raw_payload_json"] = json.dumps(p)
    assert "REJECTED_RECORD|marketplace_json|mk-invalid|VIN_FORMAT|NO_SOURCE_TIMESTAMP" in ids(detect(sr, er))


# ------------------------------------------------------------------ mode switch (real data is the default)
def test_default_is_real_data_classification(sample):
    import inspect
    assert inspect.signature(rf.detect).parameters["synthetic_fixture_mode"].default is False
    f = rf.detect(*sample)                                  # no mode argument
    cls = by_id(f)
    for vin in (TESLA, "3FA6P0H73HR123456"):
        gap = cls[f"COVERAGE_GAP|{vin}|missing:marketplace_json"]
        assert (gap["evidence_class"], gap["counts_as_actionable"]) == ("COVERAGE_UNEXPLAINED", "yes")
        assert "SYNTHETIC" not in gap["fixture_evidence"].upper()
    assert cls["COVERAGE_GAP|1N4AL3AP9JC123456|missing:dealer_csv"]["counts_as_actionable"] == "no"  # explained
    assert all(x["counts_as_actionable"] == "yes" for x in f if x["issue_type"] == "REJECTED_RECORD")
    assert sum(x["counts_as_actionable"] == "yes" for x in f) == 9
    assert ids(f) == ids(detect(*sample))                   # only classification differs, never detection


def test_default_does_not_match_the_synthetic_golden_file(sample):
    report = gc.compare(rf.detect(*sample), gc.load_golden())
    assert not report["ok"] and report["missing"] == [] and report["extra"] == []


def test_synthetic_mode_must_be_requested_explicitly_and_reproduces_all_ten(sample):
    report = gc.compare(rf.detect(*sample, synthetic_fixture_mode=True), gc.load_golden())
    assert report["ok"] and len(report["rows"]) == 10


def run_cli(*args):
    import subprocess, sys, io, csv as _csv
    out = subprocess.run([sys.executable, str(WB / "reference_findings.py"), "--sample", str(SAMPLE), *args],
                         capture_output=True, text=True, env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return out, list(_csv.DictReader(io.StringIO(out.stdout)))


def test_cli_default_is_real_data_and_flag_enables_synthetic_mode():
    out, default_rows = run_cli()
    assert out.returncode == 0 and len(default_rows) == 10
    assert not gc.compare(default_rows, gc.load_golden())["ok"]
    out, synth_rows = run_cli("--synthetic-fixtures")
    assert out.returncode == 0 and gc.compare(synth_rows, gc.load_golden())["ok"]


def test_old_real_data_flag_is_gone():
    out, _ = run_cli("--real-data")
    assert out.returncode == 2 and "unrecognized arguments" in out.stderr


# ------------------------------------------------------------------ ambiguous / missing timestamps (synthetic, isolated)
V = "2T1BU4EE9DC000001"
CAMRY = dict(year="2020", make="Toyota", model="Camry")


def base_pair(trim_b="SE"):
    return [rec(V, "dealer_csv", V, "2026-03-01T10:00:00Z", trim="SE", mileage="1000", **CAMRY),
            rec(V, "marketplace_json", "mk-1", "2026-03-02T10:00:00Z", trim=trim_b, mileage="1100", **CAMRY)]


def test_synthetic_baseline_has_no_findings():
    assert detect(base_pair(), []) == []


def test_tie_with_conflicting_value_is_ambiguous_and_not_resolved():
    rows = base_pair() + [rec(V, "dealer_csv", V, "2026-03-01T10:00:00Z", trim="LE", mileage="1000", **CAMRY)]
    f = detect(rows, [])
    assert ids(f) == {f"AMBIGUOUS_ORDER|{V}|dealer_csv|2026-03-01T10:00:00Z"}        # no conflict, no drift
    assert f[0]["field"] == "trim" and f[0]["counts_as_actionable"] == "yes"


def test_tie_that_agrees_on_the_compared_field_is_not_ambiguous():
    rows = base_pair(trim_b="XLE") + [rec(V, "dealer_csv", V, "2026-03-01T10:00:00Z", trim="SE", mileage="1000", **CAMRY)]
    assert ids(detect(rows, [])) == {f"ATTR_CONFLICT|{V}|trim|dealer_csv~marketplace_json"}


def test_tie_differing_only_in_mileage_is_ambiguous_for_mileage_only():
    rows = base_pair(trim_b="XLE") + [rec(V, "dealer_csv", V, "2026-03-01T10:00:00Z", trim="SE", mileage="5000", **CAMRY)]
    f = by_id(detect(rows, []))
    assert f[f"AMBIGUOUS_ORDER|{V}|dealer_csv|2026-03-01T10:00:00Z"]["field"] == "mileage"
    assert f"ATTR_CONFLICT|{V}|trim|dealer_csv~marketplace_json" in f           # trim comparison is still valid
    assert not [x for x in f if x.startswith("MILEAGE_REGRESSION")]            # mileage is never guessed


def test_cross_source_tie_with_different_mileage_has_star_scope_and_no_regression():
    rows = [rec(V, "dealer_csv", V, "2026-03-01T10:00:00Z", trim="SE", mileage="5000", **CAMRY),
            rec(V, "marketplace_json", "mk-1", "2026-03-01T10:00:00Z", trim="SE", mileage="4000", **CAMRY)]
    assert ids(detect(rows, [])) == {f"AMBIGUOUS_ORDER|{V}|*|2026-03-01T10:00:00Z"}


def test_ambiguity_is_independent_of_row_order():
    rows = base_pair() + [rec(V, "dealer_csv", V, "2026-03-01T10:00:00Z", trim="LE", mileage="1000", **CAMRY)]
    assert detect(rows, []) == detect(list(reversed(rows)), [])


def test_two_records_one_missing_timestamp_is_ambiguous_with_token():
    rows = base_pair() + [rec(V, "dealer_csv", V, "", trim="LE", mileage="900", **CAMRY)]
    f = by_id(detect(rows, []))
    key = f"AMBIGUOUS_ORDER|{V}|dealer_csv|NO_SOURCE_TIMESTAMP"
    assert set(f) == {key} and f[key]["timestamp_a"] == ""


def test_single_record_missing_timestamp_is_usable_and_flagged():
    rows = [rec(V, "dealer_csv", V, "", trim="SE", mileage="1000", **CAMRY),
            rec(V, "marketplace_json", "mk-1", "2026-03-02T10:00:00Z", trim="XLE", mileage="1100", **CAMRY)]
    f = by_id(detect(rows, []))
    conflict = f[f"ATTR_CONFLICT|{V}|trim|dealer_csv~marketplace_json"]
    assert conflict["timestamp_a"] == "" and "missing" in conflict["fixture_evidence"].lower()
    # VIN-wide mileage ordering needs the missing timestamp, so it is reported, not guessed
    assert f"AMBIGUOUS_ORDER|{V}|dealer_csv|NO_SOURCE_TIMESTAMP" in f and len(f) == 2


def test_missing_timestamp_never_invents_a_mileage_regression():
    rows = [rec(V, "dealer_csv", V, "", trim="SE", mileage="5000", **CAMRY),
            rec(V, "marketplace_json", "mk-1", "2026-03-02T10:00:00Z", trim="SE", mileage="100", **CAMRY)]
    assert ids(detect(rows, [])) == {f"AMBIGUOUS_ORDER|{V}|dealer_csv|NO_SOURCE_TIMESTAMP"}


def test_ingestion_time_style_columns_are_ignored():
    rows = base_pair()
    for i, r in enumerate(rows):
        r["ingested_at"] = f"2099-01-0{2 - i}T00:00:00Z"     # would reverse the order if it were used
    rows.append(rec(V, "dealer_csv", V, "2026-03-05T10:00:00Z", trim="SE", mileage="500", **CAMRY))
    regs = [x for x in detect(rows, []) if x["issue_type"] == "MILEAGE_REGRESSION"]
    assert len(regs) == 1 and (regs[0]["value_a"], regs[0]["value_b"]) == ("1100", "500")


def test_unknown_source_is_an_error_not_a_silent_skip():
    bad = base_pair()
    bad[0]["source_name"] = "mystery_feed"
    with pytest.raises(ValueError):
        detect(bad, [])
