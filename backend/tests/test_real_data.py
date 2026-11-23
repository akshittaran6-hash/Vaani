"""The shipped data in data/ (Akshit's set) and the demo scenarios that depend on it.

The other test modules check code rules on the frozen placeholder fixture; this one checks
that the real catalogue validates, seeds, and still produces the scenarios in docs/DEMO.md.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import psycopg
import pytest
from psycopg import sql

from backend.catalog.loader import DATA_DIR
from backend.catalog.models import Catalog
from backend.catalog.schedule import every_day_times
from backend.catalog.validate import validate_catalog
from backend.config import Settings
from backend.db import SQL_FILES, SUPABASE_DIR, run_sql
from backend.devdb import with_db
from backend.messaging import MockMessenger
from backend.store import Store
from backend.tests.conftest import CALLER, day
from backend.tools import ToolContext, run_tool

REAL_DB = "vaani_real_data_test"


def test_real_data_is_valid(real_catalog: Catalog) -> None:
    report = validate_catalog(real_catalog)
    assert report.errors == []
    assert len(real_catalog.restaurants) == 10 and len(real_catalog.hospitals) == 10
    assert len(real_catalog.test_calls) == 40


def test_weekday_hours_differ_but_exceptions_fit_every_day(real_catalog: Catalog) -> None:
    varying = [d for d in real_catalog.doctors if len(set(d.schedule.values())) > 1]
    assert len(varying) >= 40  # most doctors close at different times on different weekdays
    docs = {d.doctor_id: d for d in real_catalog.doctors}
    for row in real_catalog.doctor_availability:
        common = set(every_day_times(docs[row.doctor_id]))
        assert set(row.booked_times) <= common, row.doctor_id


def test_short_emergency_forms_are_covered(real_catalog: Catalog) -> None:
    """The baseline phrases merged by import_data.py keep short, common emergency forms."""
    phrases = {p.phrase for p in real_catalog.speciality_mapping.emergency_phrases}
    for p in ("chest pain", "सीने में दर्द", "gunde noppi", "behosh", "heart attack"):
        assert p in phrases


# ---------------------------------------------------------------------------
# Tools on a database seeded with the real data (supabase/seed.sql)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_url(pg_url: str) -> Iterator[str]:
    with psycopg.connect(pg_url, autocommit=True) as conn:
        conn.execute(sql.SQL("drop database if exists {}").format(sql.Identifier(REAL_DB)))
        conn.execute(sql.SQL("create database {}").format(sql.Identifier(REAL_DB)))
    url = with_db(pg_url, REAL_DB)
    with psycopg.connect(url, autocommit=True) as conn:
        for name in SQL_FILES:  # schema → rls → the committed (real) seed
            run_sql(conn, (SUPABASE_DIR / name).read_text(encoding="utf-8"))
    yield url


@pytest.fixture
async def real_ctx(real_url: str, real_catalog: Catalog) -> AsyncIterator[ToolContext]:
    with psycopg.connect(real_url, autocommit=True) as conn:
        run_sql(conn, (SUPABASE_DIR / "seed.sql").read_text(encoding="utf-8"))  # no bookings
    store = Store(real_url, max_size=5)
    await store.open()
    settings = Settings(_env_file=None, supabase_db_url=real_url, data_dir=DATA_DIR)  # type: ignore[call-arg]
    call_id = await store.start_call("phone", CALLER)
    yield ToolContext(
        store=store,
        catalog=real_catalog,
        settings=settings,
        messenger=MockMessenger(),
        call_id=call_id,
        phone=CALLER,
        language="hi",
    )
    await store.close()


def _tomorrow() -> str:
    return day(1).isoformat()


@pytest.mark.db
async def test_hindi_restaurant_demo(real_ctx: ToolContext) -> None:
    """Jubilee Hills, 6 people tomorrow: top 3 by rating; Dumgalli only has 19:00 at dinner."""
    r = await run_tool(
        real_ctx, "search_restaurants", {"area_id": "jubilee_hills", "party_size": 6, "date": _tomorrow()}
    )
    assert [x["name"] for x in r["results"]] == ["Dumgalli Courtyard", "Tandoor Taaraka", "Aavakaaya Arugu"]

    slots = await run_tool(
        real_ctx,
        "get_restaurant_slots",
        {"restaurant_id": "r_jh_01", "date": _tomorrow(), "party_size": 6, "time": "20:30"},
    )
    assert slots["requested_full"] is True
    assert [t for t in slots["free"] if t >= "19:00"] == ["19:00"]
    assert "19:00" in slots["nearest"]

    other = await run_tool(
        real_ctx,
        "get_restaurant_slots",
        {"restaurant_id": "r_jh_03", "date": _tomorrow(), "party_size": 6, "time": "20:30"},
    )
    assert other["requested_full"] is False


@pytest.mark.db
async def test_aavakaaya_deposit_for_six(real_ctx: ToolContext) -> None:
    r = await run_tool(
        real_ctx,
        "book_table",
        {"restaurant_id": "r_jh_02", "date": _tomorrow(), "time": "19:00", "party_size": 6, "name": "Pranav"},
    )
    assert r["ok"] and r["deposit_needed"] is True and r["deposit_inr"] == 300


@pytest.mark.db
async def test_pulao_pankthi_full_tomorrow_night_for_six(real_ctx: ToolContext) -> None:
    six = await run_tool(
        real_ctx, "get_restaurant_slots", {"restaurant_id": "r_gb_03", "date": _tomorrow(), "party_size": 6}
    )
    assert [t for t in six["free"] if t >= "19:00"] == []
    two = await run_tool(
        real_ctx, "get_restaurant_slots", {"restaurant_id": "r_gb_03", "date": _tomorrow(), "party_size": 2}
    )
    assert "20:30" in two["free"]  # one small table left (test call T16)


@pytest.mark.db
async def test_telugu_hospital_demo(real_ctx: ToolContext) -> None:
    """Gachibowli skin doctor tomorrow: Vaana Grove's Dr. Navisha is full, Dr. Suvin from 15:00."""
    r = await run_tool(
        real_ctx,
        "search_hospitals",
        {"area_id": "gachibowli", "speciality": "Dermatology", "date": _tomorrow()},
    )
    names = [x["name"] for x in r["results"]]
    assert names[:2] == ["Vaana Grove Hospital", "Taarika Skin and Dental Clinic"]
    assert r["results"][1]["doctor_name"] == "Dr. Vaanika Neelimodugu"

    navisha = await run_tool(real_ctx, "get_doctor_slots", {"doctor_id": "d_gb_01_derm_1", "date": _tomorrow()})
    assert navisha["fully_booked"] is True
    suvin = await run_tool(real_ctx, "get_doctor_slots", {"doctor_id": "d_gb_01_derm_2", "date": _tomorrow()})
    assert suvin["free"][0] == "15:00"


@pytest.mark.db
async def test_map_speciality_on_real_phrases(real_ctx: ToolContext) -> None:
    for text, spec in [
        ("charmam doctor kavali", "Dermatology"),
        ("dil ka doctor chahiye", "Cardiology"),
        ("heart doctor please", "Cardiology"),
        ("kanti doctor", "Ophthalmology"),
    ]:
        r = await run_tool(real_ctx, "map_speciality", {"text": text})
        assert r.get("speciality") == spec, text
    for text in ("Gundelo baaga noppi, oopiri aadatledu", "सीने में दर्द हो रहा है", "bahut khoon beh raha hai"):
        r = await run_tool(real_ctx, "map_speciality", {"text": text})
        assert r.get("emergency") is True, text


@pytest.mark.db
async def test_faq_on_real_questions(real_ctx: ToolContext) -> None:
    for biz, q, lang in [
        ("r_gb_04", "Gachibowli Pepper Pandal lo wheelchair tho lopaliki raavachaa?", "te"),  # T08
        ("h_jh_03", "Jubilee Hills Tarali Skin and Eye Clinic Sunday OPD timings enti?", "te"),  # T28
        ("h_gb_01", "Is there a lab at Vaana Grove Hospital in Gachibowli?", "en"),  # T39
    ]:
        r = await run_tool(real_ctx, "answer_faq", {"business_id": biz, "question": q, "lang": lang})
        assert r.get("answer"), q


def test_doctor_name_is_not_the_callers_name(real_catalog: Catalog) -> None:
    from backend.flows.extract import is_entity_name

    assert is_entity_name("Navisha Vaanavolu", real_catalog)  # eval T29: the doctor, not the patient
    assert is_entity_name("Dumgalli Courtyard", real_catalog)
    assert not is_entity_name("Rishvi Kalatiruma", real_catalog)
    assert not is_entity_name("Navisha", real_catalog)  # a first name alone stays a valid caller name


@pytest.mark.db
async def test_every_real_phrase_maps(real_ctx: ToolContext, real_catalog: Catalog) -> None:
    m = real_catalog.speciality_mapping
    for p in m.phrases:
        r = await run_tool(real_ctx, "map_speciality", {"text": p.phrase})
        assert r.get("speciality") == p.speciality, p.phrase
    for e in m.emergency_phrases:
        r = await run_tool(real_ctx, "map_speciality", {"text": e.phrase})
        assert r.get("emergency") is True, e.phrase


def test_repeated_doctor_first_names_are_not_guessed(real_catalog: Catalog) -> None:
    """Two Dr. Suvins (Gachibowli derm, Jubilee Hills ortho). A voice run once booked the wrong one."""
    from backend.flows.extract import find_doctor_named

    t = "Vanagrao-lo Dr. Suvin Relimudi gaaru madhyaahnam moodu gantalaki"  # real STT output
    assert getattr(find_doctor_named(t, real_catalog), "doctor_id", None) == "d_gb_01_derm_2"
    assert find_doctor_named("Dr. Suvin garu tho", real_catalog) is None  # ambiguous → ask
    jh = find_doctor_named("Dr. Suvin garu tho", real_catalog, area_id="jubilee_hills")
    assert jh is not None and jh.hospital_id.startswith("h_jh")
    derm = find_doctor_named("Dr. Suvin garu tho", real_catalog, speciality="Dermatology")
    assert derm is not None and derm.doctor_id == "d_gb_01_derm_2"


def test_stt_spellings_of_business_names(real_catalog: Catalog) -> None:
    from backend.flows.extract import find_business

    assert getattr(find_business("Vana Grove lo appointment", real_catalog), "hospital_id", None) == "h_gb_01"
    assert getattr(find_business("Dumgali Courtyard 8:30 baje", real_catalog), "restaurant_id", None) == "r_jh_01"
    assert find_business("Nenu Vaani tho matladutunna", real_catalog) is None  # not "Vaana Grove"
