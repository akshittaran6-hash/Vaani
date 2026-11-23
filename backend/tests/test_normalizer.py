"""voice/normalizer.py: digits → spoken te / hi / en-IN before TTS."""

from __future__ import annotations

import pytest

from backend.voice.normalizer import digits_words, money_words, normalize, number_words


@pytest.mark.parametrize(
    ("n", "en", "hi", "te"),
    [
        (6, "six", "chhah", "aaru"),
        (15, "fifteen", "pandrah", "padihenu"),
        (21, "twenty one", "ikkees", "iravai okati"),
        (45, "forty five", "paintaalees", "nalabhai aidu"),
        (99, "ninety nine", "ninyaanve", "tombhai tommidi"),
        (300, "three hundred", "teen sau", "moodu vandalu"),
        (650, "six hundred fifty", "chhah sau pachaas", "aaru vandala yabhai"),
        (1000, "one thousand", "ek hazaar", "veyyi"),
        (1800, "one thousand eight hundred", "ek hazaar aath sau", "veyyi enimidi vandalu"),
    ],
)
def test_number_words(n: int, en: str, hi: str, te: str) -> None:
    assert (number_words(n, "en"), number_words(n, "hi"), number_words(n, "te")) == (en, hi, te)


def test_money() -> None:
    assert money_words(650, "te") == "aaru vandala yabhai rupayalu"
    assert money_words(300, "te") == "moodu vandala rupayalu"
    assert money_words(300, "hi") == "teen sau rupaye"
    assert money_words(900, "en") == "nine hundred rupees"


@pytest.mark.parametrize(
    ("text", "lang", "spoken"),
    [
        # Hindi clock phrases
        ("Kal raat 8:30 baje", "hi", "Kal raat saadhe aath baje"),
        ("kal shaam 7, Dumgalli Courtyard", "hi", "kal shaam saat baje, Dumgalli Courtyard"),
        ("subah 10:15", "hi", "subah sava das baje"),
        ("raat 9:45", "hi", "raat paune das baje"),
        ("dopahar 1:30", "hi", "dopahar dedh baje"),
        ("dopahar 2:30", "hi", "dopahar dhaai baje"),
        ("20:30", "hi", "raat saadhe aath baje"),
        ("dopahar 3", "hi", "dopahar teen baje"),
        # Telugu
        ("repu raatri 8:30 ki", "te", "repu raatri enimidinnara ki"),
        ("madhyaanam 3 ki", "te", "madhyaanam moodu gantalaki"),
        ("podduna 10:15", "te", "podduna padi paavu"),
        ("saayantram 7:30", "te", "saayantram edunnara"),
        # English
        ("Tomorrow at 8:30 PM", "en", "Tomorrow at eight thirty PM"),
        ("at 7 PM", "en", "at seven PM"),
        ("at 7pm", "en", "at seven PM"),
        ("10:05", "en", "ten oh five AM"),
        ("19:00", "en", "seven PM"),
    ],
)
def test_times(text: str, lang: str, spoken: str) -> None:
    assert normalize(text, lang) == spoken


@pytest.mark.parametrize(
    ("text", "lang", "spoken"),
    [
        ("Booking ID VN-4821", "en", "Booking ID V N four eight two one"),
        ("Booking ID VN-4821", "hi", "Booking ID V N four eight two one"),
        ("ఐడీ VN-3799. WhatsAppలో", "te", "ఐడీ V N three seven nine nine. WhatsAppలో"),
        ("Please call 112 or 108 now", "en", "Please call one one two or one zero eight now"),
        ("112 पर कॉल करें", "hi", "one one two पर कॉल करें"),
        ("Tele-MANAS 14416", "en", "Tele-MANAS one four four one six"),
        ("₹300 deposit lagega", "hi", "teen sau rupaye deposit lagega"),
        ("fee ₹650.", "te", "fee aaru vandala yabhai rupayalu."),
        ("fee 900 rupaye", "hi", "fee nau sau rupaye"),
        ("Rs 1800 for two", "en", "one thousand eight hundred rupees for two"),
        ("6 log", "hi", "chhah log"),
        ("raat 6 logon ke liye", "hi", "raat chhah logon ke liye"),  # a party, not 6 o'clock
        ("4 mandi ki", "te", "naalugu mandi ki"),
        ("for 2 people", "en", "for two people"),
        ("rating 4.7", "en", "rating four point seven"),
        ("4.5 rating", "hi", "chaar point paanch rating"),
        ("Wed 25 Nov", "en", "Wednesday twenty fifth November"),
        ("(Tue 24 Nov)", "hi", "(Tuesday chaubees November)"),
        ("on the 25th", "en", "on the twenty fifth"),
        ("+919876543210", "en", "+nine one nine eight seven six five four three two one zero"),
        ("No numbers here.", "en", "No numbers here."),
        ("", "te", ""),
    ],
)
def test_ids_money_counts_dates(text: str, lang: str, spoken: str) -> None:
    assert normalize(text, lang) == spoken


def test_code_readbacks_have_no_digits_left() -> None:
    """Every read-back speech.py writes comes out with no digits for TTS."""
    from datetime import date, timedelta

    from backend.clock import today_ist
    from backend.flows.speech import appointment_readback, restaurant_readback

    d = today_ist() + timedelta(days=1)
    for lang in ("te", "hi", "en"):
        for t in ("19:00", "20:30", "12:30", "21:15"):
            r = restaurant_readback(lang, business="Dumgalli Courtyard", d=d, time=t, party=6, name="Pranav", deposit=300)
            a = appointment_readback(
                lang, hospital="Vaana Grove Hospital", doctor="Dr. Suvin Rellimudi", d=d, time=t, name="Lakshmi", fee=900
            )
            for line in (r, a):
                spoken = normalize(line, lang)
                assert not any(ch.isdigit() for ch in spoken), (lang, line, spoken)
    far = date.today() + timedelta(days=5)
    assert not any(ch.isdigit() for ch in normalize(far.strftime("%a %d %b"), "en"))


def test_digits_words() -> None:
    assert digits_words("0712", "hi") == "shunya saat ek do"


def test_helplines_digit_by_digit() -> None:
    assert normalize("Tele-MANAS 1-800-891-4416", "hi") == "Tele-MANAS one eight zero zero eight nine one four four one six"
