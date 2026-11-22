"""Opt-in PostgreSQL extraction integration test (Step 4).

Run:  WORKBENCH_PG_INTEGRATION=1 [WORKBENCH_PG_BIN=<dir with initdb,pg_ctl,psql>] [BASH_BIN=<bash>] pytest workbench -m pg_integration

Builds a THROWAWAY cluster (own data dir, 127.0.0.1, free port), migrates a random-named database, runs the
canonical six-step ingestion, runs extract.sh, and checks the result against the committed sample, the golden
findings and the read-only guarantees. Nothing outside the temporary directory is touched; teardown runs in
finally/atexit even when a check fails. Not compared across environments: database UUIDs (never extracted),
ingested_at (not extracted) and error_message (library text).
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import golden_compare as gc
import reference_findings as rf
from pg_harness import TempCluster, find_pg_bin

pytestmark = pytest.mark.pg_integration

WB = Path(__file__).resolve().parents[1]
SAMPLE = WB / "sample"
VOLATILE = {"ingestion_errors": {"error_message"}, "ingestion_runs": {"error_message"}}
EXPECTED_COUNTS = {"vehicles": 5, "source_records": 9, "price_observations": 9, "ingestion_runs": 6,
                   "ingestion_errors": 4}  # keyed by extract (CSV) name
TABLE_OF = {"vehicles": "vehicles", "source_records": "vehicle_source_records",
            "price_observations": "vehicle_price_observations", "ingestion_runs": "ingestion_runs",
            "ingestion_errors": "ingestion_errors"}

if os.environ.get("WORKBENCH_PG_INTEGRATION") != "1":
    pytest.skip("opt-in: set WORKBENCH_PG_INTEGRATION=1", allow_module_level=True)

PG_BIN = find_pg_bin()
if PG_BIN is None:
    pytest.fail("WORKBENCH_PG_INTEGRATION=1 but initdb/pg_ctl/psql were not found (set WORKBENCH_PG_BIN)",
                pytrace=False)
BASH = os.environ.get("BASH_BIN") or shutil.which("bash") or "bash"


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def table_fingerprints(cluster: TempCluster, db: str) -> dict[str, str]:
    """md5 over every row of every public table (content only; no volatile ids are interpreted)."""
    names = cluster.psql(db, "SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
                             "AND table_type='BASE TABLE' ORDER BY 1", readonly=True).stdout.split()
    assert names, "no tables found"
    out = {}
    for n in names:
        r = cluster.psql(db, f"SELECT count(*) || ':' || coalesce(md5(string_agg(t::text, '|' ORDER BY t::text)), '') "
                             f'FROM public."{n}" t', readonly=True)
        assert r.returncode == 0, r.stderr
        out[n] = r.stdout.strip()
    return out


def run_extract(cluster: TempCluster, db: str, out: Path, script_dir: Path | None = None):
    script = (script_dir or WB) / "extract.sh"
    env = {**os.environ, "WORKBENCH_DATABASE_URL": cluster.url(db), "PSQL": cluster.exe("psql")}
    return subprocess.run([BASH, script.as_posix(), out.as_posix()], env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=300)


class Built:
    pass


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    import generate_sample as gs  # imports asyncpg/sqlalchemy; only needed for this opt-in test

    b = Built()
    cluster = TempCluster(PG_BIN)
    try:
        cluster.start()
        b.cluster = cluster
        b.root = cluster.root
        b.db = f"workbench_it_{uuid.uuid4().hex[:8]}"
        r = cluster.psql("postgres", f'CREATE DATABASE "{b.db}"')
        assert r.returncode == 0, r.stderr

        from sqlalchemy.engine import make_url
        sa_url = make_url(cluster.url(b.db)).set(drivername="postgresql+asyncpg")
        gs.migrate(sa_url)

        async def ingest():
            engine = await gs.ingest_canonical(sa_url, b.db)
            await engine.dispose()
        asyncio.run(ingest())

        b.before = table_fingerprints(cluster, b.db)
        b.out = tmp_path_factory.mktemp("extracted") / "out"
        b.proc = run_extract(cluster, b.db, b.out)
        b.after = table_fingerprints(cluster, b.db)
        b.gs = gs
        yield b
    finally:
        cluster.stop()


# ---------------------------------------------------------------------------------------------- extraction
def test_extraction_succeeded(built):
    assert built.proc.returncode == 0, built.proc.stderr
    assert sorted(p.name for p in built.out.glob("*.csv")) == sorted(
        ["vehicles.csv", "source_records.csv", "price_observations.csv", "ingestion_runs.csv", "ingestion_errors.csv"])


@pytest.mark.parametrize("table,n", sorted(EXPECTED_COUNTS.items()))
def test_expected_counts_in_database_and_csv(built, table, n):
    r = built.cluster.psql(built.db, f"SELECT count(*) FROM {TABLE_OF[table]}", readonly=True)
    assert r.returncode == 0 and int(r.stdout.strip()) == n
    assert len(read_csv(built.out / f"{table}.csv")) == n


def test_three_distinct_rejected_records_but_four_occurrences(built):
    rows = read_csv(built.out / "ingestion_errors.csv")
    assert len(rows) == 4
    assert len({r["raw_payload_json"] for r in rows}) == 3


@pytest.mark.parametrize("table", sorted(EXPECTED_COUNTS))
def test_extract_matches_committed_sample_excluding_volatile_columns(built, table):
    drop = VOLATILE.get(table, set())

    def norm(rows):
        return [{k: v for k, v in r.items() if k not in drop} for r in rows]
    got = norm(read_csv(built.out / f"{table}.csv"))
    want = norm(read_csv(SAMPLE / f"{table}.csv"))
    assert got == want


def test_files_without_volatile_columns_are_byte_identical(built):
    for t in ("vehicles", "source_records", "price_observations"):
        assert (built.out / f"{t}.csv").read_bytes() == (SAMPLE / f"{t}.csv").read_bytes(), t


def test_meaningful_values(built):
    sr = read_csv(built.out / "source_records.csv")
    po = read_csv(built.out / "price_observations.csv")
    veh = {r["vin"]: r for r in read_csv(built.out / "vehicles.csv")}
    assert len(veh) == 5 and all(re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", v) for v in veh)
    assert {r["source_name"] for r in sr} == {"dealer_csv", "marketplace_json"}
    assert {r["source_record_id"] for r in sr if r["source_name"] == "marketplace_json"} >= {"mk-1001", "mk-1002"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", r["payload_hash"]) for r in sr)  # recomputed in validate_sample below
    # every observation has the (vin, source, timestamp) link to exactly one source record
    assert all(r["matching_source_records"] == "1" for r in po)
    # mileage values that the golden regressions depend on
    assert len(po) == 9 and all(r["mileage"] for r in po if r["source_name"] == "marketplace_json")


def test_validate_sample_passes_on_extracted_output(built):
    built.gs.write_manifest(built.out)
    r = subprocess.run([sys.executable, "-I", str(WB / "tools" / "validate_sample.py"), "--sample", str(built.out)],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------------------------- detector / golden
def test_detector_reproduces_all_ten_golden_findings_from_extracted_data(built):
    found = rf.detect(*rf.load_sample(built.out), synthetic_fixture_mode=True)
    report = gc.compare(found, gc.load_golden())
    assert report["ok"], report
    assert len(report["rows"]) == 10 and report["missing"] == [] and report["extra"] == []


def test_default_real_data_mode_on_extracted_data_finds_same_ten_but_nine_actionable(built):
    found = rf.detect(*rf.load_sample(built.out))
    assert len(found) == 10
    assert sum(f["counts_as_actionable"] == "yes" for f in found) == 9
    assert not gc.compare(found, gc.load_golden())["ok"]  # real-data classification differs from synthetic golden


# ---------------------------------------------------------------------------------------------- read-only
def test_extraction_left_every_table_unchanged(built):
    assert built.before == built.after
    for csv_name, n in EXPECTED_COUNTS.items():
        assert built.before[TABLE_OF[csv_name]].startswith(f"{n}:"), csv_name  # fingerprints cover the real tables


@pytest.mark.parametrize("stmt", [
    "INSERT INTO vehicles (vin, year, make, model) VALUES ('1HGCM82633A004352', 2003, 'x', 'y')",
    "UPDATE vehicles SET make = 'tampered'",
    "DELETE FROM vehicle_source_records",
    "TRUNCATE ingestion_errors",
    "DROP TABLE vehicle_price_observations",
    "CREATE TABLE workbench_write_probe (x int)",
])
def test_writes_are_rejected_under_the_extraction_session_options(built, stmt):
    env = {**os.environ, "PGOPTIONS": "-c default_transaction_read_only=on -c TimeZone=UTC -c statement_timeout=60000"}
    r = subprocess.run([built.cluster.exe("psql"), "-X", "-q", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=sqlstate",
                        "-d", built.cluster.url(built.db), "-c", stmt],
                       env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    assert r.returncode != 0
    assert "25006" in r.stderr  # SQLSTATE read_only_sql_transaction (a code, not library message text)
    assert table_fingerprints(built.cluster, built.db) == built.before


def test_a_write_hidden_in_an_extract_query_is_rejected_by_extract_sh(built, tmp_path):
    """A hostile SQL file run by an unmodified copy of extract.sh must fail and change nothing."""
    shutil.copyfile(WB / "extract.sh", tmp_path / "extract.sh")
    sql = tmp_path / "sql"
    sql.mkdir()
    (sql / "01_evil.sql").write_text("DELETE FROM vehicles RETURNING vin;\n", encoding="utf-8", newline="\n")
    out = tmp_path / "out"
    r = run_extract(built.cluster, built.db, out, script_dir=tmp_path)
    assert r.returncode != 0
    assert not (out / "evil.csv").exists()
    assert table_fingerprints(built.cluster, built.db) == built.before


def test_control_writes_do_succeed_without_the_read_only_option(built):
    """Guards against a vacuous read-only test: in a separate scratch database a write works when not read-only."""
    ctl = f"workbench_it_ctl_{uuid.uuid4().hex[:8]}"
    assert built.cluster.psql("postgres", f'CREATE DATABASE "{ctl}"').returncode == 0
    ok = built.cluster.psql(ctl, "CREATE TABLE t (x int); INSERT INTO t VALUES (1)")
    assert ok.returncode == 0
    ro = built.cluster.psql(ctl, "INSERT INTO t VALUES (2)", readonly=True)
    assert ro.returncode != 0
    assert built.cluster.psql(ctl, "SELECT count(*) FROM t", readonly=True).stdout.strip() == "1"


# ---------------------------------------------------------------------------------------------- isolation
def test_cluster_is_isolated_from_installed_servers_and_autostream_database(built):
    c = built.cluster
    data_dir = c.psql("postgres", "SHOW data_directory", readonly=True).stdout.strip()
    assert Path(data_dir).resolve() == c.data.resolve()
    import tempfile
    assert c.root.name.startswith("wb_pg_it_") and c.root.resolve().parent == Path(tempfile.gettempdir()).resolve()
    assert c.port not in (5432, 5433) and c.url().startswith("postgresql://postgres@127.0.0.1:")
    names = set(c.psql("postgres", "SELECT datname FROM pg_database", readonly=True).stdout.split())
    assert names >= {built.db}
    assert not {n for n in names if "autostream" in n.lower()}
    assert built.db.startswith("workbench_it_")


# ---------------------------------------------------------------------------------------------- cleanup
def test_teardown_removes_everything_even_when_a_check_fails():
    """Simulate a failing verification inside the same try/finally shape the fixture uses."""
    cluster = TempCluster(PG_BIN)
    root = port = None
    try:
        cluster.start()
        root, port = cluster.root, cluster.port
        assert cluster.is_listening()
        raise AssertionError("simulated verification failure")
    except AssertionError:
        pass
    finally:
        cluster.stop()
    assert cluster.stopped
    assert not root.exists()
    assert not cluster.is_listening()
    cluster.stop()  # idempotent


def test_teardown_after_failed_start_leaves_nothing_behind(monkeypatch):
    """initdb succeeds, then the server cannot start (pg_ctl missing): stop() must still delete the directory."""
    cluster = TempCluster(PG_BIN)
    real_exe = cluster.exe
    monkeypatch.setattr(cluster, "exe", lambda n: str(Path(PG_BIN) / "no_such_pg_ctl") if n == "pg_ctl" else real_exe(n))
    try:
        with pytest.raises(FileNotFoundError):
            cluster.start()
        assert cluster.root is not None and cluster.root.exists()
    finally:
        cluster.stop()
    assert not cluster.root.exists()
