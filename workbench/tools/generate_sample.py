"""Regenerate workbench/sample/ by running the canonical ingestion sequence in a DISPOSABLE database.

Safety rules enforced here:
  * The database is created by this script with a random name (workbench_sample_<hex>) on the server
    named by --admin-url / WORKBENCH_ADMIN_URL, which must be on localhost. There is no default server.
  * Only that database is ever migrated, written to, or dropped. Its name is never user-supplied.
  * The extraction itself runs read-only (checked below by attempting, and failing, a write).
Uses only dependencies already required by backend/requirements.txt, plus psql via extract.sh.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import asyncpg
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

REPO = Path(__file__).resolve().parents[2]
WORKBENCH = REPO / "workbench"
BACKEND = REPO / "backend"
FIXTURES = REPO / "fixtures"

# Canonical sequence: scripts/verify_codespaces.sh and backend/tests/test_postgres_integration.py.
STEPS = [
    (1, "dealer_feed_v1.csv", "csv"),
    (2, "dealer_feed_v1.csv", "csv"),   # replay
    (3, "dealer_feed_v2.csv", "csv"),
    (4, "invalid_feed.csv", "csv"),
    (5, "marketplace_feed.json", "json"),
    (6, "marketplace_feed.json", "json"),  # replay
]
STEP_NOTES = {2: "replay of step 1", 6: "replay of step 5"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migrate(sa_url) -> None:
    """alembic upgrade head against the database in sa_url (subprocess; DATABASE_URL set only for it)."""
    env = {**os.environ, "DATABASE_URL": sa_url.render_as_string(hide_password=False), "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True,
                   stdout=subprocess.DEVNULL)


async def ingest_canonical(sa_url, db_name: str):
    """Run the six canonical steps; returns the (still open) engine so the caller can dispose it."""
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from app.ingestion import ingest_csv, ingest_json  # imported late; does not open any connection

    engine = create_async_engine(sa_url)
    assert engine.url.database == db_name
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for step, fixture, kind in STEPS:
            async with maker() as session:  # one session per run, like the API
                fn = ingest_csv if kind == "csv" else ingest_json
                run_row = await fn(session, FIXTURES / fixture)
                print(f"step {step}: {fixture} -> {run_row.status} "
                      f"total={run_row.total_records} invalid={run_row.invalid_records}", file=sys.stderr)
    except BaseException:
        await engine.dispose()
        raise
    return engine


def write_manifest(out: Path) -> None:
    """Write ingestion_steps.csv and SHA256SUMS into out (which already holds the five extracts)."""
    steps_csv = ["step,fixture_file,fixture_sha256,note"]
    for step, fixture, _ in STEPS:
        steps_csv.append(f"{step},{fixture},{sha256_file(FIXTURES / fixture)},{STEP_NOTES.get(step, '')}")
    (out / "ingestion_steps.csv").write_text("\n".join(steps_csv) + "\n", encoding="utf-8", newline="\n")
    sums = [f"{sha256_file(f)}  {f.name}" for f in sorted(out.glob("*.csv"))]
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")


async def run(admin_url: str, out_dir: Path, psql: str, bash: str) -> None:
    admin = make_url(admin_url)
    if (admin.host or "localhost") not in LOCAL_HOSTS:
        sys.exit(f"refusing: admin server host {admin.host!r} is not local")
    db_name = f"workbench_sample_{uuid.uuid4().hex[:8]}"
    sync_base = admin.set(drivername="postgresql")
    sa_url = admin.set(drivername="postgresql+asyncpg", database=db_name)
    libpq_url = sync_base.set(database=db_name).render_as_string(hide_password=False)

    conn = await asyncpg.connect(
        host=admin.host, port=admin.port or 5432, user=admin.username, password=admin.password, database=admin.database or "postgres"
    )
    created = False
    engine = None
    try:
        await conn.execute(f'CREATE DATABASE "{db_name}"')
        created = True
        print(f"created disposable database {db_name}", file=sys.stderr)

        migrate(sa_url)
        engine = await ingest_canonical(sa_url, db_name)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_out = Path(tmp) / "out"
            ex_env = {**os.environ, "WORKBENCH_DATABASE_URL": libpq_url, "PSQL": psql}
            subprocess.run([bash, (WORKBENCH / "extract.sh").as_posix(), tmp_out.as_posix()], env=ex_env, check=True)

            # The extraction path must be unable to write.
            probe = subprocess.run(
                [psql, "-X", "-q", "-d", libpq_url, "-c", "CREATE TABLE workbench_write_probe (x int)"],
                env={**ex_env, "PGOPTIONS": "-c default_transaction_read_only=on"}, capture_output=True, text=True)
            if probe.returncode == 0:
                sys.exit("read-only guard failed: a write succeeded")
            print("read-only guard confirmed (write attempt rejected)", file=sys.stderr)

            write_manifest(tmp_out)

            out_dir.mkdir(parents=True, exist_ok=True)
            for f in tmp_out.iterdir():
                shutil.copyfile(f, out_dir / f.name)
    finally:
        if engine is not None:
            await engine.dispose()
        if created:
            await conn.execute(f'DROP DATABASE "{db_name}" WITH (FORCE)')
            print(f"dropped disposable database {db_name}", file=sys.stderr)
        await conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--admin-url", default=os.environ.get("WORKBENCH_ADMIN_URL"),
                   help="postgresql://user[:pw]@localhost:port/postgres on a throwaway server (required)")
    p.add_argument("--out", type=Path, default=WORKBENCH / "sample")
    p.add_argument("--psql", default=os.environ.get("PSQL") or shutil.which("psql") or "psql")
    p.add_argument("--bash", default=os.environ.get("BASH_BIN") or shutil.which("bash") or "bash")
    a = p.parse_args()
    if not a.admin_url:
        sys.exit("an admin URL for a disposable local server is required (--admin-url or WORKBENCH_ADMIN_URL)")
    asyncio.run(run(a.admin_url, a.out, a.psql, a.bash))


if __name__ == "__main__":
    main()
