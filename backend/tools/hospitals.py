"""Hospital tools: map_speciality, search_hospitals, get_doctor_slots, book_appointment."""

from __future__ import annotations

import datetime as dt
from datetime import date, time
from typing import Any, Literal

import psycopg
from pydantic import Field
from rapidfuzz import fuzz

from backend.catalog.models import DAYS, SPECIALITIES, Catalog, Doctor, EmergencyPhrase, Speciality
from backend.clock import is_past, today_ist, window
from backend.text import norm
from backend.tools.base import Args, Result, ToolContext, ToolError, day_word, require_area, require_window, tool
from backend.tools.restaurants import MAX_RESULTS, db_error, hhmm

EMERGENCY_FUZZY_CUTOFF = 90  # one wrong letter in ten ("chest pane"); higher misses typos
SPECIALITY_FUZZY_CUTOFF = 88

# Plain names callers use for the department itself.
SPECIALITY_NAMES = {
    "general medicine": "General Medicine",
    "physician": "General Medicine",
    "dermatology": "Dermatology",
    "gynecology": "Gynecology",
    "gynaecology": "Gynecology",
    "gynac": "Gynecology",
    "pediatrics": "Pediatrics",
    "paediatrics": "Pediatrics",
    "pediatrician": "Pediatrics",
    "orthopedics": "Orthopedics",
    "ortho": "Orthopedics",
    "orthopaedic": "Orthopedics",
    "ent": "ENT",
    "cardiology": "Cardiology",
    "dental": "Dental",
    "ophthalmology": "Ophthalmology",
    "ophthalmologist": "Ophthalmology",
}


def _contains(haystack: str, needle: str) -> bool:
    return bool(needle) and f" {needle} " in f" {haystack} "


def _window_score(text: str, phrase: str) -> float:
    """Best fuzz.ratio between `phrase` and any run of the same number of words in `text`.

    Comparing whole word windows (not partial substrings) means 'chest pane' still matches
    'chest pain', but 'घुटने में दर्द' (knee pain) no longer matches 'सीने में दर्द'
    (chest pain) just because they share 'ने में दर्द'.
    """
    words, n = text.split(), len(phrase.split())
    if len(words) < n:
        return fuzz.ratio(text, phrase)
    return max(fuzz.ratio(" ".join(words[i : i + n]), phrase) for i in range(len(words) - n + 1))


def _find_phrase(text: str, phrases: list[EmergencyPhrase], fuzzy: bool = True) -> str | None:
    t = norm(text)
    for e in phrases:
        p = norm(e.phrase)
        if _contains(t, p) or (fuzzy and len(p) >= 6 and _window_score(t, p) >= EMERGENCY_FUZZY_CUTOFF):
            return e.phrase
    return None


def find_emergency(text: str, catalog: Catalog) -> str | None:
    """The emergency phrase found in `text` (exact, or one letter off), else None.

    Shared by map_speciality and the session's pre-LLM guard, so both always agree.
    """
    return _find_phrase(text, catalog.speciality_mapping.emergency_phrases)


def find_self_harm(text: str, catalog: Catalog) -> str | None:
    """A self-harm / suicidal-thoughts phrase in `text` (whole phrase, exact), else None.

    No fuzzy matching here: one letter turns "karna chahta hoon" (I want to do) into
    "marna chahta hoon" (I want to die), and "jana nahi chahta" into "jeena nahi chahta",
    so a fuzzy match would give ordinary booking callers the helpline reply."""
    m = catalog.speciality_mapping
    return _find_phrase(text, m.self_harm_phrases, fuzzy=False) if m.self_harm_reply else None


def self_harm_reply(catalog: Catalog, lang: str) -> str:
    reply = catalog.speciality_mapping.self_harm_reply
    assert reply is not None
    return str(getattr(reply, lang if lang in ("te", "hi", "en") else "en"))


def find_speciality_phrase(text: str, catalog: Catalog) -> str | None:
    """Exact speciality phrase in the text ("pallu noppi" → Dental), else None. No fuzzy."""
    t = norm(text)
    phrases = {norm(p.phrase): p.speciality for p in catalog.speciality_mapping.phrases} | SPECIALITY_NAMES
    hits = [p for p in phrases if _contains(t, p)]
    return phrases[max(hits, key=len)] if hits else None


def doctor(ctx: ToolContext, doctor_id: str) -> Doctor:
    d = next((x for x in ctx.catalog.doctors if x.doctor_id == doctor_id), None)
    if d is None:
        raise ToolError("UNKNOWN_DOCTOR", f"No doctor {doctor_id}")
    return d


# ---------------------------------------------------------------------------


class MapSpecialityArgs(Args):
    text: str
    lang: Literal["te", "hi", "en"] | None = None


@tool("map_speciality", MapSpecialityArgs, "Plain words → speciality. Emergencies are detected first.")
async def map_speciality(ctx: ToolContext, a: MapSpecialityArgs) -> tuple[Result, str]:
    text = norm(a.text)
    m = ctx.catalog.speciality_mapping
    lang = a.lang or ctx.language
    reply = getattr(m.emergency_reply, lang if lang in ("te", "hi", "en") else "en")

    # 0. Self-harm: a gentle reply with Tele-MANAS 14416 and 112. Never a booking.
    if hit := find_self_harm(a.text, ctx.catalog):
        return {
            "emergency": True,
            "self_harm": True,
            "matched": hit,
            "reply": self_harm_reply(ctx.catalog, lang),
        }, "Self-harm words → gave Tele-MANAS 14416 and 112, no booking"

    # 1. Emergency always wins (CLAUDE.md rule 7): exact phrase, then near-identical spelling.
    if hit := find_emergency(a.text, ctx.catalog):
        return {
            "emergency": True,
            "matched": hit,
            "reply": reply,
        }, f"Emergency phrase “{hit}” → told caller to call 108 / 112"

    # 2. Longest exact phrase or department name inside the utterance.
    phrases = {norm(p.phrase): p.speciality for p in m.phrases} | SPECIALITY_NAMES
    hits = [p for p in phrases if _contains(text, p)]
    if hits:
        best = max(hits, key=len)
        return {"speciality": phrases[best], "matched": best}, f"“{a.text}” → {phrases[best]}"

    # 3. Fuzzy, for mis-heard words.
    scored = [(_window_score(text, p), p) for p in phrases if len(p) >= 6]
    score, best_p = max(scored, default=(0.0, ""))
    if score >= SPECIALITY_FUZZY_CUTOFF:
        return {"speciality": phrases[best_p], "matched": best_p}, f"“{a.text}” → {phrases[best_p]} (fuzzy)"
    return {"unknown": True, "specialities": list(SPECIALITIES)}, f"“{a.text}” → no speciality matched"


# ---------------------------------------------------------------------------

FREE_SQL = """
select s.doctor_id, s.date, s.time
  from public.doctor_slots s
  join public.doctors d on d.doctor_id = s.doctor_id
 where s.doctor_id = any (%(ids)s) and s.status = 'free'
   and s.date between %(from)s and %(to)s
   and not (s.date = any (d.on_leave_dates))
 order by s.doctor_id, s.date, s.time
"""


async def next_free(ctx: ToolContext, ids: list[str], start: date) -> dict[str, tuple[date, time]]:
    _, last = window()
    rows = await ctx.store.fetch(FREE_SQL, {"ids": ids, "from": start, "to": last})
    first: dict[str, tuple[date, time]] = {}
    for r in rows:
        if r["doctor_id"] not in first and not is_past(r["date"], r["time"]):
            first[r["doctor_id"]] = (r["date"], r["time"])
    return first


class SearchHospitalsArgs(Args):
    area_id: str
    speciality: Speciality
    date: dt.date | None = None


@tool(
    "search_hospitals",
    SearchHospitalsArgs,
    "Top 3 hospitals with a doctor of that speciality and their next free slot.",
)
async def search_hospitals(ctx: ToolContext, a: SearchHospitalsArgs) -> tuple[Result, str]:
    area_name = require_area(ctx, a.area_id)
    start = a.date or today_ist()
    require_window(start)
    hospitals = {
        h.hospital_id: h for h in ctx.catalog.hospitals if h.area_id == a.area_id and a.speciality in h.specialities
    }
    docs = [d for d in ctx.catalog.doctors if d.hospital_id in hospitals and d.speciality == a.speciality]
    free = await next_free(ctx, [d.doctor_id for d in docs], start)

    best: dict[str, tuple[Doctor, date, time]] = {}
    for d in docs:
        if d.doctor_id in free:
            fd, ft = free[d.doctor_id]
            cur = best.get(d.hospital_id)
            if cur is None or (fd, ft) < (cur[1], cur[2]):
                best[d.hospital_id] = (d, fd, ft)

    results: list[dict[str, Any]] = []
    for h in sorted(hospitals.values(), key=lambda x: -x.rating):
        if h.hospital_id not in best:
            continue
        d, fd, ft = best[h.hospital_id]
        results.append(
            {
                "hospital_id": h.hospital_id,
                "name": h.name,
                "rating": h.rating,
                "highlight": h.highlight,
                "doctor_id": d.doctor_id,
                "doctor_name": d.name,
                "fee_inr": d.consultation_fee_inr,
                "next_free": {"date": fd.isoformat(), "time": hhmm(ft)},
                "window": d.schedule.get(DAYS[fd.weekday()]),  # type: ignore[call-overload]
            }
        )
        if len(results) == MAX_RESULTS:
            break
    out: Result = {"results": results}
    if not results:
        out["reason"] = "no_availability"
    return (
        out,
        f"Searched {a.speciality} → {len(results)} hospital{'s' if len(results) != 1 else ''}"
        f" in {area_name} (from {day_word(start)})",
    )


class DoctorSlotsArgs(Args):
    doctor_id: str
    date: dt.date


@tool("get_doctor_slots", DoctorSlotsArgs, "Free times for a doctor on a date (leave and blocks respected).")
async def get_doctor_slots(ctx: ToolContext, a: DoctorSlotsArgs) -> tuple[Result, str]:
    d = doctor(ctx, a.doctor_id)
    require_window(a.date)
    leave = await ctx.store.fetchrow(
        "select on_leave_dates from public.doctors where doctor_id = %(d)s", {"d": d.doctor_id}
    )
    on_leave = bool(leave and a.date in (leave["on_leave_dates"] or []))
    rows = await ctx.store.fetch(
        "select time, status from public.doctor_slots where doctor_id = %(d)s and date = %(dt)s order by time",
        {"d": d.doctor_id, "dt": a.date},
    )
    free = (
        [] if on_leave else [hhmm(r["time"]) for r in rows if r["status"] == "free" and not is_past(a.date, r["time"])]
    )
    out: Result = {
        "doctor_id": d.doctor_id,
        "date": a.date.isoformat(),
        "free": free,
        "on_leave": on_leave,
        "fully_booked": bool(rows) and not free and not on_leave,
        "next_free_date": None,
    }
    if not free:
        later = await next_free(ctx, [d.doctor_id], a.date + dt.timedelta(days=1))
        if d.doctor_id in later:
            out["next_free_date"] = later[d.doctor_id][0].isoformat()
            out["next_free_time"] = hhmm(later[d.doctor_id][1])
    if on_leave:
        summary = f"Checked {d.name} → on leave {day_word(a.date)}"
    elif not free:
        summary = f"Checked {d.name} → fully booked {day_word(a.date)}"
    else:
        summary = f"Checked {d.name} slots → {len(free)} free {day_word(a.date)} (first {free[0]})"
    return out, summary


class BookAppointmentArgs(Args):
    doctor_id: str
    date: dt.date
    time: dt.time
    name: str = Field(min_length=1, max_length=80)
    phone: str | None = None


@tool("book_appointment", BookAppointmentArgs, "Book a doctor's slot (only after the caller confirmed the read-back).")
async def book_appointment(ctx: ToolContext, a: BookAppointmentArgs) -> tuple[Result, str]:
    d = doctor(ctx, a.doctor_id)
    require_window(a.date)
    phone = a.phone or ctx.phone
    if not phone:
        raise ToolError("MISSING_DETAILS", "No phone number for this call")
    try:
        row = await ctx.store.fetchrow(
            "select * from public.book_appointment(%(d)s, %(dt)s, %(t)s, %(n)s, %(ph)s, %(lang)s, %(src)s, %(call)s)",
            {
                "d": d.doctor_id,
                "dt": a.date,
                "t": a.time,
                "n": a.name,
                "ph": phone,
                "lang": ctx.language,
                "src": "vaani_call" if ctx.call_id else "web",
                "call": ctx.call_id,
            },
        )
    except psycopg.errors.RaiseException as e:
        raise db_error(e) from e
    assert row is not None
    if ctx.call_id:
        await ctx.emit(
            "booking_created",
            {
                "booking_id": row["booking_id"],
                "service": "hospital",
                "business_id": row["hospital_id"],
                "doctor_id": d.doctor_id,
                "date": a.date.isoformat(),
                "time": hhmm(a.time),
                "language": ctx.language,
            },
        )
    return (
        {"booking_id": row["booking_id"], "fee_inr": row["fee_inr"], "hospital_id": row["hospital_id"]},
        f"Booked {d.name} · {hhmm(a.time)} {day_word(a.date)} · ID {row['booking_id']}",
    )
