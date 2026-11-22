"""Temporary PostgreSQL cluster for the opt-in integration test.

A throwaway cluster with its OWN data directory (initdb), bound to 127.0.0.1 on a free port, trust auth,
no unix socket. It never reads or touches any installed cluster or the AutoStream database. Teardown is
idempotent and is also registered with atexit, so a failed run or an interrupted pytest still cleans up.
"""
from __future__ import annotations

import atexit
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

EXE = ".exe" if os.name == "nt" else ""


def find_pg_bin() -> Path | None:
    """Directory holding initdb/pg_ctl/psql: WORKBENCH_PG_BIN, else PATH."""
    cands = []
    if os.environ.get("WORKBENCH_PG_BIN"):
        cands.append(Path(os.environ["WORKBENCH_PG_BIN"]))
    on_path = shutil.which("pg_ctl")
    if on_path:
        cands.append(Path(on_path).parent)
    for c in cands:
        if all((c / f"{n}{EXE}").exists() for n in ("initdb", "pg_ctl", "psql")):
            return c
    return None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TempCluster:
    def __init__(self, pg_bin: Path):
        self.bin = pg_bin
        self.root: Path | None = None
        self.port = 0
        self.started = False
        self.stopped = False  # set by stop(); lets tests assert clean shutdown

    # ------------------------------------------------------------------ paths / urls
    @property
    def data(self) -> Path:
        return self.root / "data"

    def url(self, database: str = "postgres") -> str:
        return f"postgresql://postgres@127.0.0.1:{self.port}/{database}"

    def exe(self, name: str) -> str:
        return str(self.bin / f"{name}{EXE}")

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> "TempCluster":
        atexit.register(self.stop)
        self.root = Path(tempfile.mkdtemp(prefix="wb_pg_it_"))
        self.port = free_port()
        log = self.root / "initdb.log"
        with open(log, "wb") as fh:
            subprocess.run([self.exe("initdb"), "-D", str(self.data), "-U", "postgres", "-A", "trust", "-E", "UTF8"],
                           stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, check=True, timeout=180)
        opts = f"-p {self.port} -c listen_addresses=127.0.0.1 -c fsync=off -c max_connections=30"
        if os.name != "nt":
            opts += f" -c unix_socket_directories={self.root}"
        # Output goes to files (never pipes): a pipe inherited by the postmaster makes pg_ctl hang on Windows.
        with open(self.root / "pg_ctl.log", "wb") as fh:
            subprocess.run([self.exe("pg_ctl"), "start", "-D", str(self.data), "-w", "-t", "60",
                            "-l", str(self.root / "server.log"), "-o", opts],
                           stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, check=True, timeout=120)
        self.started = True
        return self

    def stop(self) -> None:
        """Stop the server and delete the whole directory. Safe to call repeatedly or after a failed start."""
        if self.stopped or self.root is None:
            return
        if (self.data / "postmaster.pid").exists():
            with open(os.devnull, "wb") as dn:
                subprocess.run([self.exe("pg_ctl"), "stop", "-D", str(self.data), "-m", "immediate", "-w", "-t", "30"],
                               stdin=subprocess.DEVNULL, stdout=dn, stderr=dn, timeout=60)
            self._kill_leftover()
        for _ in range(20):  # Windows may hold files briefly after exit
            shutil.rmtree(self.root, ignore_errors=True)
            if not self.root.exists():
                break
            time.sleep(0.5)
        self.stopped = True

    def _kill_leftover(self) -> None:
        pid_file = self.data / "postmaster.pid"
        if not pid_file.exists():
            return
        try:
            pid = int(pid_file.read_text().splitlines()[0])
        except (OSError, ValueError, IndexError):
            return
        deadline = time.time() + 10
        while time.time() < deadline and pid_file.exists():
            time.sleep(0.3)
        if pid_file.exists():  # still there: force-kill that exact pid (our own postmaster only)
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=30)
                else:
                    os.kill(pid, 9)
            except OSError:
                pass
            time.sleep(1)

    def is_listening(self) -> bool:
        with socket.socket() as s:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", self.port)) == 0

    # ------------------------------------------------------------------ helpers
    def psql(self, database: str, sql: str, readonly: bool = False) -> subprocess.CompletedProcess:
        env = {**os.environ}
        if readonly:
            env["PGOPTIONS"] = "-c default_transaction_read_only=on"
        return subprocess.run([self.exe("psql"), "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1",
                               "-d", self.url(database), "-c", sql],
                              env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
