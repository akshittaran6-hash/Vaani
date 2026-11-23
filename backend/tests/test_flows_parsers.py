"""Language detection and te/hi/en date-time parsing (no DB, no LLM)."""

from __future__ import annotations

from datetime import date

import pytest

from backend.flows.language import detect_language
from backend.flows.when import parse_day, parse_time

TODAY = date(2026, 11, 22)  # a Sunday


@pytest.mark.parametrize(
    ("text", "kind", "expected"),
    [
        ("8:30 chalega", "restaurant", "20:30"),
        ("saadhe aath baje", "restaurant", "20:30"),
        ("enimidinnara ki", "restaurant", "20:30"),
        ("okati gantaki", "restaurant", "13:00"),
        ("7:30 pm", "restaurant", "19:30"),
        ("raat 9 baje", "restaurant", "21:00"),
        ("around 9 pm", "restaurant", "21:00"),
        ("sava saat", "restaurant", "19:15"),
        ("8.30", "restaurant", "20:30"),
        ("lunch at 1:30", "restaurant", "13:30"),
        ("11 ki", "hospital", "11:00"),
        ("saayantram 4:30", "hospital", "16:30"),
        ("12 noon", "hospital", "12:00"),
        ("noon", "hospital", "12:00"),
        ("10:15", "hospital", "10:15"),
        ("shaam 6 baje", "hospital", "18:00"),
        ("subah 9 baje", "hospital", "09:00"),
        ("podduna padakondu gantalaki", "hospital", "11:00"),
        ("20:30", "restaurant", "20:30"),
        ("Udayam clinic, shaam 6 baje.", "hospital", "18:00"),  # "udayam" (morning) is a clinic name here
        ("lunch ki aaruguru, naalugu rojula tarvata, okati gantaki", "restaurant", "13:00"),
        ("Cyber Valley, saayantram 4:30. Ledu, 5:30 ki marchandi.", "hospital", "16:30"),
        ("no time here", "restaurant", None),
    ],
)
def test_parse_time(text: str, kind: str, expected: str | None) -> None:
    assert parse_time(text, kind) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("text", "offset"),
    [
        ("kal raat 6 logon ke liye", 1),
        ("repu lunch", 1),
        ("tomorrow evening", 1),
        ("parso", 2),
        ("ellundi rathri", 2),
        ("day after tomorrow", 2),
        ("3 din baad", 3),
        ("naalugu rojula tarvata", 4),
        ("mudu rojula tarvata", 3),
        ("in 3 days", 3),
        ("three days from now", 3),
        ("aaj", 0),
        ("ivala", 0),
        ("ee saturday", 6),
        ("Sunday", 0),
        ("shanivar ko", 6),
    ],
)
def test_parse_day(text: str, offset: int) -> None:
    got = parse_day(text, TODAY)
    assert got is not None and (got - TODAY).days == offset


def test_latest_time_takes_the_correction() -> None:
    from backend.flows.when import latest_time

    assert latest_time("Cyber Valley, saayantram 4:30. Ledu, 5:30 ki marchandi.", "hospital") == "17:30"
    assert latest_time("7 nahi, raat 9 baje kar do", "restaurant") == "21:00"


def test_parse_day_iso_and_unknown() -> None:
    assert parse_day("2026-11-25", TODAY) == date(2026, 11, 25)
    assert parse_day("whenever", TODAY) is None


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("Jubilee Hills lo manchi restaurant cheppu", "te"),
        ("Kukatpally lo dermatologist kavali, repu", "te"),
        ("Jubilee Hills mein koi achha restaurant batao", "hi"),
        ("Dil ka doctor chahiye Jubilee Hills mein, parso", "hi"),
        ("I need a table for two at Green Leaf", "en"),
        ("జూబ్లీ హిల్స్", "te"),
        ("दांत दर्द", "hi"),
    ],
)
def test_detect_language(text: str, lang: str) -> None:
    assert detect_language(text)[0] == lang


def test_language_split_of_test_calls_mostly_matches(catalog: object) -> None:
    """Sanity check against the 40 scripted calls: the first caller line predicts the language mix."""
    from backend.catalog.models import Catalog

    assert isinstance(catalog, Catalog)
    want = {"te-en": "te", "hi-en": "hi", "en-IN": "en"}
    hits = sum(detect_language(t.caller_turns[0])[0] == want[t.language_mix] for t in catalog.test_calls)
    assert hits >= 34, hits  # ≥ 85% from one sentence; the agent can still switch later


def test_clock_freeze_pins_now_and_today() -> None:
    from datetime import date, datetime, time

    from backend import clock

    at = datetime.combine(date(2026, 12, 5), time(9, 0), clock.IST)
    clock.freeze(at)
    try:
        assert clock.now_ist() == at and clock.today_ist() == date(2026, 12, 5)
        assert clock.is_past(date(2026, 12, 5), time(8, 45)) and not clock.is_past(date(2026, 12, 5), time(12, 30))
    finally:
        clock.freeze(None)
    assert clock.frozen_at() is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Forms from the real test calls (eval on Akshit's data, 23 Nov)
        ("ee roju night naluguriki", 4),
        ("ee roju lunch lo mugguram vastam", 3),
        ("12:30 pm ki mugguriki book cheyandi", 3),
        ("repu raatri eight thirty ki aaruguriki table kavali", 6),
        ("repu yedintiki iddaram vastam", 2),
        ("Actually iddaru kaadu, naluguru", 4),
        ("for six tomorrow at lunch", 6),
        ("Change that to four, please. 12:30 pm is fine.", 4),  # eval T19
        ("Make it eight pm instead", None),
        ("Change that to four, please.", 4),
        ("Make it 7:30 instead of 9", None),
        ("Kal dinner ke liye aath logon ki table chahiye", 8),
    ],
)
def test_parse_party_real_forms(text: str, expected: int | None) -> None:
    from backend.flows.extract import parse_party

    assert parse_party(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Anuvi Selavolu peru meeda pettandi.", "Anuvi Selavolu"),
        ("Reyan Dharavolu ke naam se rakh dijiye.", "Reyan Dharavolu"),
        ("Please put it under Ilaari Moonalapalli.", "Ilaari Moonalapalli"),
        ("Patient ka naam Rishvi Kalatiruma hai.", "Rishvi Kalatiruma"),
        ("Patient peru Esha Tallavolu.", "Esha Tallavolu"),
        ("The patient’s name is Navon Koyalagunta.", "Navon Koyalagunta"),
        ("Sare, Aavakaaya Arugu lo 12:30 pm ki book cheyandi.", None),
    ],
)
def test_parse_name_real_forms(text: str, expected: str | None) -> None:
    from backend.flows.extract import parse_name

    assert parse_name(text) == expected


def test_parson_is_day_after_tomorrow() -> None:
    assert parse_day("Parson Jubilee Hills mein chaar logon ke liye", TODAY) == date(2026, 11, 24)
