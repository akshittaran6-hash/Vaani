"""Seed SQL generation and slot expansion (no database needed)."""

from __future__ import annotations

from datetime import date

from backend.catalog.models import Catalog
from backend.catalog.schedule import doctor_times, restaurant_times
from backend.catalog.seeding import arr, build_seed_sql, preview, q
from backend.db import SUPABASE_DIR


def test_sql_literals_escape_quotes() -> None:
    assert q("Children's Clinic") == "'Children''s Clinic'"
    assert q(None) == "null" and q(True) == "true" and q(4.5) == "4.5"
    assert arr([]) == "'{}'::text[]"
    assert arr(["T1", "it's"]) == "array['T1', 'it''s']::text[]"


def test_restaurant_times_respect_opening_hours(catalog: Catalog) -> None:
    cafe = next(r for r in catalog.restaurants if r.restaurant_id == "r_gb_01")  # open 08:00-23:00
    assert restaurant_times(cafe, "mon") == [
        "12:30",
        "13:00",
        "13:30",
        "14:00",
        "19:00",
        "19:30",
        "20:00",
        "20:30",
        "21:00",
        "21:30",
    ]
    jade = next(r for r in catalog.restaurants if r.restaurant_id == "r_jh_05")  # lunch from 12:30
    assert restaurant_times(jade, "tue")[0] == "12:30"


def test_doctor_times_stop_before_range_end(catalog: Catalog) -> None:
    doc = next(d for d in catalog.doctors if d.schedule.get("mon") == "10:00-13:00")
    times = doctor_times(doc, "mon")
    assert times[0] == "10:00" and times[-1] == "12:45" and len(times) == 12
    part_week = next(d for d in catalog.doctors if len(d.schedule) < 7)
    missing = next(day for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun") if day not in part_week.schedule)
    assert doctor_times(part_week, missing) == []


def test_seed_sql_is_relative_and_deterministic(catalog: Catalog) -> None:
    sql = build_seed_sql(catalog)
    assert sql == build_seed_sql(catalog)
    assert sql.startswith("-- GENERATED") and "begin;" in sql and sql.rstrip().endswith("commit;")
    assert "public.vaani_today() + v.day_offset" in sql
    # No absolute dates leak in.
    assert "2026-" not in sql


def test_committed_seed_sql_is_up_to_date(real_catalog: Catalog) -> None:
    committed = (SUPABASE_DIR / "seed.sql").read_text(encoding="utf-8")
    assert committed == build_seed_sql(real_catalog), "run: uv run python scripts/make_seed_sql.py"


def test_preview_counts_and_no_skips_for_valid_data(catalog: Catalog) -> None:
    # Every weekday as "today": the weekday rule means no exception is ever skipped.
    for day in range(7):
        pv = preview(catalog, date(2026, 11, 23 + day))
        assert pv.skipped == []
        assert pv.restaurant_slots == 7 * sum(len(restaurant_times(r, "mon")) for r in catalog.restaurants)
        assert pv.doctor_slots > 0


def test_preview_reports_exceptions_outside_hours(catalog: Catalog) -> None:
    # A part-week doctor's exception falls on a non-working day for some "today".
    part_week = next(d for d in catalog.doctors if len(d.schedule) < 7)
    from backend.catalog.models import DoctorSlotException

    bad = catalog.model_copy(
        update={
            "doctor_availability": [
                DoctorSlotException(doctor_id=part_week.doctor_id, day_offset=0, booked_times=["10:00"])
            ]
        }
    )
    skipped = [s for day in range(7) for s in preview(bad, date(2026, 11, 23 + day)).skipped]
    assert skipped and part_week.doctor_id in skipped[0]
