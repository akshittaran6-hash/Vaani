"""Throwaway Postgres for tests, eval and the CLI (no Docker needed).

Starts a temporary cluster from local `initdb` / `pg_ctl` binaries, applies schema → rls →
seed into a template database, and hands out fresh copies (`create database … template`)
so every eval call starts from identical data. Never points at a real database.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg import sql

from backend.db import SQL_FILES, SUPABASE_DIR, run_sql

PG_BIN_CANDIDATES = [
    "/opt/homebrew/opt/postgresql@17/bin",
    "/opt/homebrew/opt/postgresql@16/bin",
    "/opt/homebrew/opt/postgresql@15/bin",
    "/usr/local/opt/postgresql@15/bin",
    "/usr/lib/postgresql/17/bin",
    "/usr/lib/postgresql/16/bin",
    "/usr/lib/postgresql/15/bin",
]
TEMPLATE_DB = "vaani_template"


def pg_bin() -> Path | None:
    found = shutil.which("initdb")
    if found:
        return Path(found).parent
    return next((Path(c) for c in PG_BIN_CANDIDATES if (Path(c) / "initdb").exists()), None)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def ephemeral_cluster() -> Iterator[str]:
    """Yields a superuser URL to the cluster's `postgres` database; deletes everything after."""
    bin_dir = pg_bin()
    if bin_dir is None:
        raise RuntimeError("No Postgres binaries found (brew install postgresql@16)")
    tmp = Path(tempfile.mkdtemp(prefix="vaani-pg-"))
    data, port = tmp / "data", _free_port()
    # macOS: postgres refuses to start without a valid locale; UTF8 for Telugu/Devanagari.
    env = {**os.environ, "LC_ALL": "C", "LANG": "C"}

    def run(*cmd: object) -> None:
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=env)
        if r.returncode != 0:
            log = (tmp / "pg.log").read_text() if (tmp / "pg.log").exists() else ""
            raise RuntimeError(f"{cmd[0]} failed:\n{r.stdout}\n{r.stderr}\n{log[-2000:]}")

    run(bin_dir / "initdb", "-D", data, "-U", "postgres", "-A", "trust", "--no-sync", "--locale=C", "--encoding=UTF8")
    # No Unix socket: macOS temp paths exceed the 103-byte socket path limit.
    opts = f"-p {port} -c unix_socket_directories='' -c listen_addresses=127.0.0.1 -c fsync=off -c max_connections=300"
    run(bin_dir / "pg_ctl", "-D", data, "-l", tmp / "pg.log", "-w", "-o", opts, "start")
    try:
        yield f"postgresql://postgres@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run(
            [str(bin_dir / "pg_ctl"), "-D", str(data), "-m", "immediate", "stop"], capture_output=True, env=env
        )
        shutil.rmtree(tmp, ignore_errors=True)


def with_db(url: str, dbname: str) -> str:
    return url.rsplit("/", 1)[0] + "/" + dbname


def apply_all(url: str) -> None:
    with psycopg.connect(url, autocommit=True) as conn:
        for name in SQL_FILES:
            run_sql(conn, (SUPABASE_DIR / name).read_text(encoding="utf-8"))


def make_template(admin_url: str) -> str:
    """Create + seed the template database once; returns its URL."""
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {}").format(sql.Identifier(TEMPLATE_DB)))
        conn.execute(sql.SQL("create database {}").format(sql.Identifier(TEMPLATE_DB)))
    url = with_db(admin_url, TEMPLATE_DB)
    apply_all(url)
    return url


def freeze_db(admin_url: str, name: str, at: datetime) -> None:
    """Make vaani_now_ist() / vaani_today() in database `name` return `at` (IST wall time)."""
    stamp = at.strftime("%Y-%m-%d %H:%M:%S")
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            sql.SQL("alter database {} set vaani.now_ist = {}").format(sql.Identifier(name), sql.Literal(stamp))
        )


def clone(admin_url: str, name: str) -> str:
    """Fresh, seeded copy of the template (milliseconds)."""
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {}").format(sql.Identifier(name)))
        conn.execute(
            sql.SQL("create database {} template {}").format(sql.Identifier(name), sql.Identifier(TEMPLATE_DB))
        )
    return with_db(admin_url, name)
