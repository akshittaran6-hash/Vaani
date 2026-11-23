"""Shared fixtures.

Unit and DB tests run on a frozen copy of the original placeholder data
(`fixtures/placeholder_data/`, seeded from SQL built in memory), so code-rule tests don't
change whenever data/ is regenerated. Tests of the real shipped data use `real_catalog`
(test_real_data.py).

DB tests (marker `db`) need Postgres. They use, in order:
1. VAANI_TEST_DB_URL if set (a database the tests may WIPE — never your dev database), else
2. a throwaway Postgres cluster started from local `initdb`/`pg_ctl` binaries, else
3. they are skipped.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.catalog.loader import DATA_DIR, load_catalog
from backend.catalog.models import Catalog
from backend.catalog.seeding import build_seed_sql

FIXTURE_DATA = Path(__file__).resolve().parent / "fixtures" / "placeholder_data"

PG_BIN_CANDIDATES = [
    "/opt/homebrew/opt/postgresql@17/bin",
    "/opt/homebrew/opt/postgresql@16/bin",
    "/opt/homebrew/opt/postgresql@15/bin",
    "/usr/local/opt/postgresql@15/bin",
    "/usr/lib/postgresql/16/bin",
    "/usr/lib/postgresql/15/bin",
]


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    """The placeholder fixture catalogue (what the DB fixtures are seeded with)."""
    return load_catalog(FIXTURE_DATA)


@pytest.fixture(scope="session")
def real_catalog() -> Catalog:
    """The shipped data in data/."""
    return load_catalog(DATA_DIR)


def _pg_bin() -> Path | None:
    found = shutil.which("initdb")
    if found:
        return Path(found).parent
    for c in PG_BIN_CANDIDATES:
        if (Path(c) / "initdb").exists():
            return Path(c)
    return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    url = os.environ.get("VAANI_TEST_DB_URL")
    if url:
        yield url
        return
    bin_dir = _pg_bin()
    if bin_dir is None:
        pytest.skip("no Postgres available (set VAANI_TEST_DB_URL or install postgresql)")
    tmp = Path(tempfile.mkdtemp(prefix="vaani-pg-"))
    data, port = tmp / "data", _free_port()
    # macOS: postgres refuses to start without a valid locale in the environment.
    env = {**os.environ, "LC_ALL": "C", "LANG": "C"}

    def run(*cmd: object) -> None:
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=env)
        if r.returncode != 0:
            log = (tmp / "pg.log").read_text() if (tmp / "pg.log").exists() else ""
            raise RuntimeError(f"{cmd[0]} failed:\n{r.stdout}\n{r.stderr}\n{log[-2000:]}")

    run(bin_dir / "initdb", "-D", data, "-U", "postgres", "-A", "trust", "--no-sync", "--locale=C", "--encoding=UTF8")
    run(
        bin_dir / "pg_ctl",
        "-D",
        data,
        "-l",
        tmp / "pg.log",
        "-w",
        "-o",
        f"-p {port} -k {tmp} -c listen_addresses=127.0.0.1 -c fsync=off -c timezone=UTC",
        "start",
    )
    try:
        yield f"postgresql://postgres@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run(
            [str(bin_dir / "pg_ctl"), "-D", str(data), "-m", "immediate", "stop"], capture_output=True, env=env
        )
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Phase 2: seeded database, async store, tool context, API client
# ---------------------------------------------------------------------------

from collections.abc import AsyncIterator  # noqa: E402
from datetime import date, timedelta  # noqa: E402

import httpx  # noqa: E402
import psycopg  # noqa: E402

from backend.api.app import create_app  # noqa: E402
from backend.api.deps import Services  # noqa: E402
from backend.clock import today_ist  # noqa: E402
from backend.config import Settings  # noqa: E402
from backend.db import SQL_FILES, SUPABASE_DIR, run_sql  # noqa: E402
from backend.messaging import MockMessenger  # noqa: E402
from backend.store import Store  # noqa: E402
from backend.tools import ToolContext  # noqa: E402

CALLER = "+919876543210"
WEBHOOK_SECRET = "whsec_test_only"
SEED_SQL = build_seed_sql(load_catalog(FIXTURE_DATA))


@pytest.fixture(scope="session")
def seeded_url(pg_url: str) -> str:
    """schema → rls → seed applied once, exactly like scripts/db_apply.py."""
    with psycopg.connect(pg_url, autocommit=True) as conn:
        for name in SQL_FILES:
            run_sql(conn, (SUPABASE_DIR / name).read_text(encoding="utf-8"))
    return pg_url


@pytest.fixture
def reseed(seeded_url: str) -> None:
    """Fresh catalogue + no bookings before each test that uses it."""
    with psycopg.connect(seeded_url, autocommit=True) as conn:
        run_sql(conn, SEED_SQL)


@pytest.fixture
def settings(seeded_url: str) -> Settings:
    # _env_file=None: tests never read the developer's .env
    return Settings(
        _env_file=None,
        supabase_db_url=seeded_url,
        payment_webhook_secret=WEBHOOK_SECRET,  # type: ignore[call-arg]
        dev_simulate=True,
        public_base_url="https://vaani.test",
        data_dir=FIXTURE_DATA,
    )


@pytest.fixture(scope="session")
async def store(seeded_url: str) -> AsyncIterator[Store]:
    s = Store(seeded_url, max_size=25)
    await s.open()
    yield s
    await s.close()


@pytest.fixture
def messenger() -> MockMessenger:
    return MockMessenger()


@pytest.fixture
async def ctx(
    reseed: None, store: Store, catalog: Catalog, settings: Settings, messenger: MockMessenger
) -> ToolContext:
    call_id = await store.start_call("phone", CALLER)
    return ToolContext(
        store=store,
        catalog=catalog,
        settings=settings,
        messenger=messenger,
        call_id=call_id,
        phone=CALLER,
        language="hi",
    )


@pytest.fixture
def services(store: Store, catalog: Catalog, settings: Settings, messenger: MockMessenger) -> Services:
    return Services(settings=settings, store=store, catalog=catalog, messenger=messenger)


@pytest.fixture
async def client(reseed: None, services: Services) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(services=services)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


def day(offset: int) -> date:
    return today_ist() + timedelta(days=offset)
