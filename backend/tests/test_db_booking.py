"""Schema + seed + atomic booking functions against a real Postgres (marker: db).

Runs schema.sql and rls.sql exactly as scripts/db_apply.py does, plus the seed of the placeholder fixture data, then checks
the booking rules and a concurrent race. Uses a throwaway cluster (see conftest.py).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import date, time, timedelta

import psycopg
import pytest

from backend.catalog.models import Catalog
from backend.db import SQL_FILES, SUPABASE_DIR, run_sql
from backend.tests.conftest import SEED_SQL

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def seeded(seeded_url: str) -> str:
    return seeded_url


@pytest.fixture
def conn(seeded: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(seeded, autocommit=True) as c:
        # Each test starts from a clean booking state.
        run_sql(c, SEED_SQL)
        yield c


def today(conn: psycopg.Connection) -> date:
    row = conn.execute("select public.vaani_today()").fetchone()
    assert row is not None
    return row[0]  # type: ignore[no-any-return]


def error_code(exc: pytest.ExceptionInfo[psycopg.Error]) -> str:
    return str(exc.value.diag.message_primary)


def book_table(
    conn: psycopg.Connection, rid: str, d: date, t: str, party: int, name: str = "Test"
) -> tuple[str, str, bool, int]:
    row = conn.execute(
        "select * from public.book_table(%s, %s, %s::time, %s, %s, %s)", (rid, d, t, party, name, "+910000000000")
    ).fetchone()
    assert row is not None
    return row


def book_appt(conn: psycopg.Connection, did: str, d: date, t: str) -> tuple[str, int, str]:
    row = conn.execute(
        "select * from public.book_appointment(%s, %s, %s::time, %s, %s)", (did, d, t, "Test", "+910000000000")
    ).fetchone()
    assert row is not None
    return row


# ---------------------------------------------------------------------------


def test_apply_is_idempotent(seeded: str) -> None:
    with psycopg.connect(seeded, autocommit=True) as c:
        for name in SQL_FILES:
            run_sql(c, (SUPABASE_DIR / name).read_text(encoding="utf-8"))


def test_seed_counts_match_catalog(conn: psycopg.Connection, catalog: Catalog) -> None:
    def count(table: str) -> int:
        row = conn.execute(f"select count(*) from public.{table}").fetchone()
        assert row is not None
        return int(row[0])

    assert count("areas") == 2
    assert count("restaurants") == 10 and count("hospitals") == 10
    assert count("doctors") == len(catalog.doctors)
    assert count("restaurant_tables") == sum(len(r.tables) for r in catalog.restaurants)
    assert count("speciality_map") == len(catalog.speciality_mapping.phrases) + len(
        catalog.speciality_mapping.emergency_phrases
    )
    assert count("bookings") == 0
    # Slots cover exactly today .. today+6
    row = conn.execute("select min(date), max(date) from public.restaurant_slots").fetchone()
    assert row is not None and row[0] == today(conn) and row[1] == today(conn) + timedelta(days=6)


def test_seed_applies_exceptions(conn: psycopg.Connection) -> None:
    d = today(conn) + timedelta(days=1)
    row = conn.execute(
        "select cardinality(booked_table_ids) from public.restaurant_slots where restaurant_id='r_jh_01' and date=%s and time='20:00'",
        (d,),
    ).fetchone()
    assert row is not None and row[0] == 10  # Spice Garden fully booked tomorrow 20:00
    row = conn.execute("select on_leave_dates from public.doctors where doctor_id='d_gb_02_genmed_1'").fetchone()
    assert row is not None and row[0] == [today(conn) + timedelta(days=2)]
    row = conn.execute(
        "select count(*) filter (where status='booked'), count(*) from public.doctor_slots where doctor_id='d_jh_02_derm_1' and date=%s",
        (d,),
    ).fetchone()
    assert row is not None and row[0] == row[1] == 12  # fully booked tomorrow


def test_book_table_happy_path_picks_smallest_fitting_table(conn: psycopg.Connection) -> None:
    d = today(conn) + timedelta(days=1)
    booking_id, table_id, deposit, amount = book_table(conn, "r_jh_01", d, "20:30", 6, "Pranav")
    assert booking_id.startswith("VN-") and len(booking_id) == 7
    assert table_id in {"T7", "T8"}  # the 6-seaters
    assert deposit is False and amount == 0
    slot = conn.execute(
        "select booked_table_ids from public.restaurant_slots where restaurant_id='r_jh_01' and date=%s and time='20:30'",
        (d,),
    ).fetchone()
    assert slot is not None and table_id in slot[0]
    b = conn.execute(
        "select status, party_size, phone from public.bookings where booking_id=%s", (booking_id,)
    ).fetchone()
    assert b == ("confirmed", 6, "+910000000000")


def test_book_table_deposit(conn: psycopg.Connection) -> None:
    d = today(conn) + timedelta(days=3)
    booking_id, _, deposit, amount = book_table(conn, "r_jh_01", d, "20:30", 10)
    assert deposit is True and amount == 500
    row = conn.execute(
        "select status, amount_due_inr from public.bookings where booking_id=%s", (booking_id,)
    ).fetchone()
    assert row == ("pending_payment", 500)


@pytest.mark.parametrize(
    ("rid", "offset", "t", "party", "code"),
    [
        ("r_jh_01", 1, "20:00", 2, "SLOT_FULL"),  # demo slot is fully booked
        ("r_jh_05", 2, "20:30", 10, "PARTY_TOO_LARGE"),  # Jade Lantern max 8
        ("r_jh_02", 2, "13:00", 2, "BLOCKED"),  # staff-blocked slot
        ("r_jh_01", 1, "17:00", 2, "INVALID_TIME"),  # not a bookable start time
        ("r_xx_99", 1, "20:00", 2, "UNKNOWN_BUSINESS"),
    ],
)
def test_book_table_rules(conn: psycopg.Connection, rid: str, offset: int, t: str, party: int, code: str) -> None:
    with pytest.raises(psycopg.errors.RaiseException) as exc:
        book_table(conn, rid, today(conn) + timedelta(days=offset), t, party)
    assert error_code(exc) == code


def test_book_table_rejects_the_past(conn: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.RaiseException) as exc:
        book_table(conn, "r_jh_01", today(conn) - timedelta(days=1), "20:00", 2)
    assert error_code(exc) == "INVALID_TIME"


def test_frozen_clock_setting(conn: psycopg.Connection) -> None:
    """The eval freezes "now" with vaani.now_ist; the booking functions must follow it."""
    d = today(conn)
    try:
        conn.execute("select set_config('vaani.now_ist', %s, false)", (f"{d} 09:00:00",))
        row = conn.execute("select public.vaani_now_ist(), public.vaani_today()").fetchone()
        assert row is not None and str(row[0]) == f"{d} 09:00:00" and row[1] == d
        book_table(conn, "r_jh_01", d, "12:30", 2)  # still ahead of a frozen 09:00
        conn.execute("select set_config('vaani.now_ist', %s, false)", (f"{d} 23:00:00",))
        with pytest.raises(psycopg.errors.RaiseException) as exc:
            book_table(conn, "r_jh_01", d, "21:30", 2)
        assert error_code(exc) == "INVALID_TIME"
    finally:
        conn.execute("select set_config('vaani.now_ist', '', false)")


def test_book_appointment_rules(conn: psycopg.Connection) -> None:
    d1, d2 = today(conn) + timedelta(days=1), today(conn) + timedelta(days=2)
    booking_id, fee, hospital = book_appt(conn, "d_gb_01_derm_1", d1, "11:00")
    assert fee == 600 and hospital == "h_gb_01"
    row = conn.execute(
        "select status, amount_due_inr from public.bookings where booking_id=%s", (booking_id,)
    ).fetchone()
    assert row == ("pending_payment", 600)

    cases = [
        ("d_gb_01_derm_1", d1, "11:00", "SLOT_TAKEN"),
        ("d_jh_02_derm_1", d1, "10:00", "SLOT_TAKEN"),  # fully booked tomorrow
        ("d_gb_02_genmed_1", d2, "11:00", "DOCTOR_ON_LEAVE"),
        ("d_gb_01_cardio_1", d1, "10:00", "BLOCKED"),
        ("d_gb_01_derm_1", d1, "15:00", "INVALID_TIME"),
    ]
    for did, d, t, code in cases:
        with pytest.raises(psycopg.errors.RaiseException) as exc:
            book_appt(conn, did, d, t)
        assert error_code(exc) == code, (did, t)


def test_cancel_frees_table_and_slot(conn: psycopg.Connection) -> None:
    d = today(conn) + timedelta(days=1)
    bid, table_id, _, _ = book_table(conn, "r_jh_01", d, "19:30", 6)
    conn.execute("select public.cancel_booking(%s)", (bid,))
    conn.execute("select public.cancel_booking(%s)", (bid,))  # idempotent
    slot = conn.execute(
        "select booked_table_ids from public.restaurant_slots where restaurant_id='r_jh_01' and date=%s and time='19:30'",
        (d,),
    ).fetchone()
    assert slot is not None and table_id not in slot[0]
    # The freed table can be booked again.
    assert book_table(conn, "r_jh_01", d, "19:30", 6)[1] == table_id

    aid, _, _ = book_appt(conn, "d_gb_01_derm_1", d, "12:00")
    conn.execute("select public.cancel_booking(%s)", (aid,))
    row = conn.execute(
        "select status from public.doctor_slots where doctor_id='d_gb_01_derm_1' and date=%s and time='12:00'", (d,)
    ).fetchone()
    assert row == ("free",)


def test_unique_index_blocks_direct_double_booking(conn: psycopg.Connection) -> None:
    """Even code that bypasses the functions can't double-book a table."""
    d = today(conn) + timedelta(days=1)
    _, table_id, _, _ = book_table(conn, "r_jh_01", d, "20:30", 6)
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "insert into public.bookings (booking_id, service, business_id, date, time, party_size, table_id, name, phone)"
            " values ('VN-0001', 'restaurant', 'r_jh_01', %s, '20:30', 6, %s, 'X', '+91')",
            (d, table_id),
        )


def _race(url: str, n: int, fn: str, args: tuple[object, ...]) -> list[str]:
    """Fire n concurrent calls at the same slot; return 'ok' or the error code per call."""
    barrier = threading.Barrier(n)
    results: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        with psycopg.connect(url, autocommit=True) as c:
            barrier.wait()
            try:
                c.execute(f"select * from public.{fn}", args)
                outcome = "ok"
            except psycopg.errors.RaiseException as e:
                outcome = str(e.diag.message_primary)
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_race_twenty_callers_one_doctor_slot(conn: psycopg.Connection, seeded: str) -> None:
    d = today(conn) + timedelta(days=3)
    results = _race(
        seeded, 20, "book_appointment(%s, %s, %s::time, %s, %s)", ("d_gb_03_ent_1", d, "10:15", "Caller", "+91")
    )
    assert results.count("ok") == 1
    assert set(results) == {"ok", "SLOT_TAKEN"}
    row = conn.execute(
        "select count(*) from public.bookings where doctor_id='d_gb_03_ent_1' and date=%s and time='10:15' and status<>'cancelled'",
        (d,),
    ).fetchone()
    assert row == (1,)


def test_race_twenty_callers_last_big_table(conn: psycopg.Connection, seeded: str) -> None:
    """r_jh_01 has exactly one 12-seat table (T10): 20 parties of 10 race for it."""
    d = today(conn) + timedelta(days=3)
    results = _race(
        seeded, 20, "book_table(%s, %s, %s::time, %s, %s, %s)", ("r_jh_01", d, "20:30", 10, "Caller", "+91")
    )
    assert results.count("ok") == 1
    assert set(results) == {"ok", "SLOT_FULL"}
    row = conn.execute(
        "select booked_table_ids from public.restaurant_slots where restaurant_id='r_jh_01' and date=%s and time='20:30'",
        (d,),
    ).fetchone()
    assert row is not None and row[0].count("T10") == 1


def test_booking_time_type(conn: psycopg.Connection) -> None:
    bid, *_ = book_table(conn, "r_gb_03", today(conn) + timedelta(days=1), "13:00", 4)
    row = conn.execute("select time from public.bookings where booking_id=%s", (bid,)).fetchone()
    assert row == (time(13, 0),)
