"""Deterministic spoken text: read-backs and times in te / hi / en.

The read-back the caller says "yes" to is built HERE from the exact booking arguments,
never paraphrased by the LLM, so what Vaani reads back is exactly what gets booked.
Phase 4's normalizer will turn these into fully spoken words for TTS.
"""

from __future__ import annotations

from datetime import date

from backend.clock import today_ist

PART_OF_DAY = {
    "te": [(12, "podduna"), (16, "madhyaanam"), (19, "saayantram"), (24, "raatri")],
    "hi": [(12, "subah"), (16, "dopahar"), (19, "shaam"), (24, "raat")],
}
DAY_NAMES = {
    "te": {0: "ivala", 1: "repu", 2: "ellundi"},
    "hi": {0: "aaj", 1: "kal", 2: "parso"},
    "en": {0: "today", 1: "tomorrow", 2: "day after tomorrow"},
}


def spoken_time(hhmm: str, lang: str) -> str:
    """'20:30' → 'raat 8:30' (hi) / 'raatri 8:30' (te) / '8:30 PM' (en)."""
    h, m = int(hhmm[:2]), int(hhmm[3:])
    clock = f"{h % 12 or 12}:{m:02d}" if m else f"{h % 12 or 12}"
    if lang == "en":
        return f"{clock} {'AM' if h < 12 else 'PM'}" if m else f"{clock} {'AM' if h < 12 else 'PM'}"
    part = next(word for limit, word in PART_OF_DAY.get(lang, PART_OF_DAY["hi"]) if h < limit)
    return f"{part} {clock}"


def spoken_day(d: date, lang: str) -> str:
    delta = (d - today_ist()).days
    word = DAY_NAMES.get(lang, DAY_NAMES["en"]).get(delta)
    return word or d.strftime("%a %d %b")


def restaurant_readback(lang: str, *, business: str, d: date, time: str, party: int, name: str, deposit: int) -> str:
    day, t = spoken_day(d, lang), spoken_time(time, lang)
    if lang == "te":
        dep = f", ₹{deposit} deposit untundi" if deposit else ""
        return f"{day} {t} ki {business} lo {party} mandi ki, {name} garu peru meeda{dep}. Confirm cheyyana?"
    if lang == "hi":
        dep = f", ₹{deposit} deposit lagega" if deposit else ""
        return f"{day} {t}, {business}, {party} log, {name} ji ke naam pe{dep}. Confirm karoon?"
    dep = f"; there's a ₹{deposit} deposit" if deposit else ""
    return f"{business}, {day} at {t}, {party} people, under {name}{dep}. Shall I confirm?"


def appointment_readback(lang: str, *, hospital: str, doctor: str, d: date, time: str, name: str, fee: int) -> str:
    day, t = spoken_day(d, lang), spoken_time(time, lang)
    if lang == "te":
        return f"{day} {t} ki {doctor} garu tho, {hospital} lo, {name} garu peru meeda, fee ₹{fee}. Confirm cheyyana?"
    if lang == "hi":
        return f"{day} {t} {doctor} ke saath, {hospital} mein, {name} ji ke naam pe, fee ₹{fee}. Confirm karoon?"
    return f"{day.capitalize()} at {t} with {doctor} at {hospital}, under {name}; the fee is ₹{fee}. Shall I confirm?"
