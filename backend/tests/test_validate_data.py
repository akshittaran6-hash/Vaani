"""validate_data: the shipped placeholder data passes, and each broken variant is caught."""

from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from backend.catalog.loader import DATA_DIR, CatalogLoadError, load_raw, parse_catalog
from backend.catalog.models import Catalog
from backend.catalog.validate import validate_catalog
from scripts import validate_data


def test_placeholder_data_is_valid(catalog: Catalog) -> None:
    report = validate_catalog(catalog)
    assert report.errors == []
    assert report.warnings == []


def test_counts_match_the_brief(catalog: Catalog) -> None:
    assert len(catalog.restaurants) == 10 and len(catalog.hospitals) == 10
    assert len(catalog.test_calls) == 40
    assert len(catalog.speciality_mapping.phrases) >= 60
    assert len(catalog.speciality_mapping.emergency_phrases) >= 30


def test_demo_call_slot_is_full_with_neighbours_free(catalog: Catalog) -> None:
    """CALL_FLOW.md Hindi sample: Spice Garden tomorrow 20:00 full, 19:30 and 20:30 fit 6."""
    spice = next(r for r in catalog.restaurants if r.name == "Spice Garden")
    rows = {
        (a.day_offset, a.time): a for a in catalog.restaurant_availability if a.restaurant_id == spice.restaurant_id
    }
    all_tables = {t.table_id for t in spice.tables}
    assert set(rows[(1, "20:00")].booked_table_ids) == all_tables
    for t in ("19:30", "20:30"):
        booked = set(rows[(1, t)].booked_table_ids) if (1, t) in rows else set()
        assert any(tb.capacity >= 6 and tb.table_id not in booked for tb in spice.tables)


# ---------------------------------------------------------------------------
# Mutations: each must produce an error mentioning `needle`.
# ---------------------------------------------------------------------------

Raw = dict[str, Any]


def _drop_restaurant(raw: Raw) -> None:
    raw["restaurants"].pop()


def _unknown_area(raw: Raw) -> None:
    raw["restaurants"][0]["area_id"] = "banjara_hills"


def _bad_table(raw: Raw) -> None:
    raw["restaurant_availability"][0]["booked_table_ids"].append("T99")


def _unknown_restaurant(raw: Raw) -> None:
    raw["restaurant_availability"][0]["restaurant_id"] = "r_xx_99"


def _sample_flag(raw: Raw) -> None:
    raw["doctors"][0]["is_sample_data"] = False


def _time_outside_schedule(raw: Raw) -> None:
    raw["doctor_availability"][0]["booked_times"].append("23:45")


def _time_only_on_some_weekdays(raw: Raw) -> None:
    """Hours may differ per weekday, but an exception must be a slot on all of them."""
    row = raw["doctor_availability"][0]
    doc = next(d for d in raw["doctors"] if d["doctor_id"] == row["doctor_id"])
    start, end = doc["schedule"]["sat"].split("-")
    h, m = map(int, end.split(":"))
    doc["schedule"]["sat"] = f"{start}-{h + 1:02d}:{m:02d}"  # Saturday runs an hour longer
    row["booked_times"].append(end)  # first slot after the usual close: Saturday only


def _part_week_doctor_in_availability(raw: Raw) -> None:
    did = raw["doctor_availability"][0]["doctor_id"]
    doc = next(d for d in raw["doctors"] if d["doctor_id"] == did)
    doc["schedule"].pop("sun")


def _doctor_wrong_speciality(raw: Raw) -> None:
    raw["doctors"][0]["speciality"] = "Dental"


def _unknown_doctor_in_test(raw: Raw) -> None:
    call = next(t for t in raw["test_calls"] if t["expected"]["doctor_id"])
    call["expected"]["doctor_id"] = "d_xx_01_derm_9"


def _missing_phrase_key(raw: Raw) -> None:
    raw["agent_phrases"] = [p for p in raw["agent_phrases"] if p["key"] != "never_ask_otp"]


def _greeting_without_disclosure(raw: Raw) -> None:
    g = next(p for p in raw["agent_phrases"] if p["key"] == "greeting_with_ai_disclosure")
    g["en-IN"][0] = "Hello, how can I help?"


def _party_bigger_than_tables(raw: Raw) -> None:
    raw["restaurants"][0]["booking_rules"]["max_party_size"] = 40


def _closed_day(raw: Raw) -> None:
    raw["restaurants"][0]["opening_hours"]["mon"] = []


def _emergency_reply_without_108(raw: Raw) -> None:
    raw["speciality_mapping"]["emergency_reply"]["en"] = "Please go to a hospital."


def _too_few_phrases(raw: Raw) -> None:
    raw["speciality_mapping"]["phrases"] = raw["speciality_mapping"]["phrases"][:10]


MUTATIONS: list[tuple[Callable[[Raw], None], str]] = [
    (_drop_restaurant, "need exactly 5"),
    (_unknown_area, "unknown area_id"),
    (_bad_table, "booked table T99 does not exist"),
    (_unknown_restaurant, "unknown restaurant_id"),
    (_sample_flag, "is_sample_data must be true"),
    (_time_outside_schedule, "not a slot on every weekday"),
    (_time_only_on_some_weekdays, "not a slot on every weekday"),
    (_part_week_doctor_in_availability, "must work all 7 days"),
    (_doctor_wrong_speciality, "is not offered by"),
    (_unknown_doctor_in_test, "unknown doctor_id"),
    (_missing_phrase_key, "missing key never_ask_otp"),
    (_greeting_without_disclosure, "must say Vaani is an AI"),
    (_party_bigger_than_tables, "bigger than the largest table"),
    (_closed_day, "no bookable time on mon"),
    (_emergency_reply_without_108, "must mention 108 and 112"),
    (_too_few_phrases, "need >= 60"),
]


@pytest.fixture(scope="module")
def raw() -> Raw:
    return load_raw()


@pytest.mark.parametrize(("mutate", "needle"), MUTATIONS, ids=[m.__name__.strip("_") for m, _ in MUTATIONS])
def test_validator_catches(raw: Raw, mutate: Callable[[Raw], None], needle: str) -> None:
    broken = copy.deepcopy(raw)
    mutate(broken)
    report = validate_catalog(parse_catalog(broken))
    assert any(needle in e for e in report.errors), report.errors


def test_schema_errors_name_the_record(raw: Raw) -> None:
    broken = copy.deepcopy(raw)
    broken["restaurants"][0]["food_type"] = "vegan"
    broken["restaurants"][1]["surprise_field"] = 1
    with pytest.raises(CatalogLoadError) as exc:
        parse_catalog(broken)
    text = str(exc.value)
    assert "restaurants.json [r_jh_01].food_type" in text
    assert "surprise_field" in text


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert validate_data.main([str(DATA_DIR)]) == 0

    bad = tmp_path / "data"
    shutil.copytree(DATA_DIR, bad)
    (bad / "areas.json").write_text("{not json", encoding="utf-8")
    assert validate_data.main([str(bad)]) == 1
    assert "invalid JSON" in capsys.readouterr().out

    rows = json.loads((DATA_DIR / "restaurants.json").read_text(encoding="utf-8"))
    rows[0]["is_sample_data"] = False
    (bad / "areas.json").write_text((DATA_DIR / "areas.json").read_text(encoding="utf-8"), encoding="utf-8")
    (bad / "restaurants.json").write_text(json.dumps(rows), encoding="utf-8")
    assert validate_data.main([str(bad)]) == 1
