"""Conversation nodes for Vaani: router → restaurant | hospital.

The shapes mirror Pipecat Flows on purpose (NodeConfig: role/task messages + functions;
FlowsFunctionSchema: name, description, properties, required, handler → (result, next_node)),
so Phase 4 wraps these same nodes in a Pipecat FlowManager instead of rewriting them.

Handlers take the caller's own words for areas, dates and times and resolve them in code
(resolve_area, parse_day, parse_time). The LLM never does calendar maths, never invents
IDs, and can only book after a read-back confirmed on a later turn.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

from rapidfuzz import fuzz, process

from backend.catalog.models import SPECIALITIES, Doctor, Hospital, Restaurant
from backend.clock import today_ist
from backend.flows.context import Pending
from backend.flows.speech import appointment_readback, restaurant_readback, spoken_time
from backend.flows.when import parse_day, parse_time
from backend.tools import run_tool

if TYPE_CHECKING:
    from backend.flows.session import Session

Result = dict[str, Any]
Handler = Callable[["Session", dict[str, Any]], Awaitable[tuple[Result, str | None]]]


@dataclass(frozen=True)
class FunctionSpec:
    """Same fields as pipecat_flows.FlowsFunctionSchema."""

    name: str
    description: str
    properties: dict[str, Any]
    required: list[str]
    handler: Handler


@dataclass(frozen=True)
class NodeSpec:
    """Same idea as pipecat_flows.NodeConfig (role_message is added by the session)."""

    name: str
    task: str
    functions: list[FunctionSpec] = field(default_factory=list)


def _str(desc: str, enum: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "string", "description": desc}
    if enum:
        out["enum"] = enum
    return out


def _int(desc: str) -> dict[str, Any]:
    return {"type": "integer", "description": desc}


def err(code: str, message: str, **extra: Any) -> Result:
    return {"ok": False, "error": code, "message": message, **extra}


# ---------------------------------------------------------------------------
# Resolving the caller's words in code
# ---------------------------------------------------------------------------


def resolve_date(s: Session, text: str | None) -> date | None:
    if text:
        return parse_day(str(text), today_ist())
    current = s.ctx.slots.get("date")
    return date.fromisoformat(current) if current else None


def resolve_time(text: str | None, kind: str) -> str | None:
    if not text:
        return None
    t = str(text).strip()
    if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
        return t
    return parse_time(t, "hospital" if kind == "hospital" else "restaurant")


def find_restaurant(s: Session, ref: str | None) -> Restaurant | None:
    named = s.ctx.slots.get("business_id")
    if s.ctx.named_turn == s.ctx.turn and named and str(named).startswith("r_"):
        ref = named  # the caller named it in this turn: code wins over the LLM's argument
    ref = (ref or named or "").strip()
    rest = s.catalog.restaurants
    by_id = next((r for r in rest if r.restaurant_id == ref), None)
    if by_id or not ref:
        return by_id
    names = {r.restaurant_id: " ".join([r.name, *r.name_aliases]) for r in rest}
    hit = process.extractOne(ref, names, scorer=fuzz.WRatio, score_cutoff=75)
    return next(r for r in rest if r.restaurant_id == hit[2]) if hit else None


def find_hospital(s: Session, ref: str | None) -> Hospital | None:
    ref = (ref or "").strip()
    hosp = s.catalog.hospitals
    by_id = next((h for h in hosp if h.hospital_id == ref), None)
    if by_id or not ref:
        return by_id
    names = {h.hospital_id: " ".join([h.name, *h.name_aliases]) for h in hosp}
    hit = process.extractOne(ref, names, scorer=fuzz.WRatio, score_cutoff=75)
    return next(h for h in hosp if h.hospital_id == hit[2]) if hit else None


def find_doctor(s: Session, ref: str | None) -> Doctor | None:
    named = s.ctx.slots.get("doctor_id")
    if s.ctx.named_turn == s.ctx.turn and named:
        ref = named
    ref = (ref or named or "").strip()
    docs = s.catalog.doctors
    by_id = next((d for d in docs if d.doctor_id == ref), None)
    if by_id or not ref:
        return by_id
    clean = re.sub(r"\b(dr|doctor|garu|ji)\b\.?", " ", ref.lower())
    names = {d.doctor_id: d.name.replace("Dr. ", "") for d in docs}
    hit = process.extractOne(clean, names, scorer=fuzz.WRatio, score_cutoff=70)
    return next(d for d in docs if d.doctor_id == hit[2]) if hit else None


def caller_time(s: Session, kind: str) -> str | None:
    """The latest time the caller said, in any turn (code wins over the LLM's argument)."""
    return s.ctx.heard_time


def caller_day(s: Session) -> date | None:
    return date.fromisoformat(s.ctx.heard_day) if s.ctx.heard_day else None


def caller_name(s: Session, llm_name: Any) -> str:
    """The caller's name, only if the CALLER said it: the extracted slot, or an LLM-suggested
    name that literally appears in something the caller said (blocks "Aapka naam" / "Guest")."""
    if s.ctx.slots.get("name"):
        return str(s.ctx.slots["name"])
    name = str(llm_name or "").strip()
    said = " ".join(t["text"].lower() for t in s.ctx.transcript if t["speaker"] == "caller")
    return name if name and all(w in said for w in name.lower().split()) else ""


def spoken_list(times: list[str], lang: str) -> list[str]:
    return [spoken_time(t, lang) for t in times]


async def resolve_area_words(s: Session, area: str | None) -> tuple[str | None, Result | None]:
    """Area id for the caller's words, or (None, an 'unsupported' result to speak)."""
    area = (area or s.ctx.slots.get("area_id") or "").strip()
    if not area:
        return None, err("ASK_AREA", "Ask which area: Jubilee Hills or Gachibowli")
    if area in s.settings.demo_areas:
        return area, None
    r = await run_tool(s.tools, "resolve_area", {"text": area})
    if r.get("unsupported"):
        s.ctx.unsupported_heard = str(r["heard"])
        lang = s.ctx.language
        return None, {
            "ok": False,
            "error": "UNSUPPORTED_AREA",
            "heard": r["heard"],
            "force_say": r["reply"].get(lang, r["reply"]["en"]),
        }
    await s.set_slot("area_id", r["area_id"])
    return str(r["area_id"]), None


# ---------------------------------------------------------------------------
# Global functions (every node)
# ---------------------------------------------------------------------------


async def set_language(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    lang = str(a.get("lang", ""))
    if lang not in ("te", "hi", "en"):
        return err("INVALID_ARGS", "lang must be te, hi or en"), None
    await s.set_language(lang, via="agent")
    return {"ok": True, "language": lang}, None


async def switch_service(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    to = str(a.get("to", ""))
    if to not in ("restaurant", "hospital"):
        return err("INVALID_ARGS", "to must be restaurant or hospital"), None
    r = await run_tool(s.tools, "switch_service", {"to": to, "reason": str(a.get("reason", ""))})
    s.ctx.service = to  # type: ignore[assignment]
    s.ctx.pending = None
    return r, to


async def transfer_to_human(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    r = await run_tool(s.tools, "transfer_to_human", {"reason": str(a.get("reason", ""))})
    s.ctx.transferred = True
    return {**r, "say_this": s.phrase("transfer_to_human")}, None


async def end_call(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    r = await run_tool(s.tools, "end_call", {"reason": str(a.get("reason", ""))})
    s.ctx.ended = True
    return {**r, "say_this": s.phrase("goodbye")}, None


GLOBAL_FUNCTIONS = [
    FunctionSpec(
        "set_language",
        "Caller switched language. Use te, hi or en.",
        {"lang": _str("te | hi | en", ["te", "hi", "en"])},
        ["lang"],
        set_language,
    ),
    FunctionSpec(
        "switch_service",
        "Caller wants the other service.",
        {"to": _str("restaurant | hospital", ["restaurant", "hospital"]), "reason": _str("why")},
        ["to"],
        switch_service,
    ),
    FunctionSpec("transfer_to_human", "Caller asks for a person.", {"reason": _str("why")}, [], transfer_to_human),
    FunctionSpec(
        "end_call",
        "Caller is done / said bye, or after abuse or 3 off-topic turns.",
        {"reason": _str("why")},
        [],
        end_call,
    ),
]


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


SERVICE_SYNONYMS = {
    "restaurant": "restaurant",
    "food": "restaurant",
    "table": "restaurant",
    "dining": "restaurant",
    "dinner": "restaurant",
    "hospital": "hospital",
    "doctor": "hospital",
    "clinic": "hospital",
    "medical": "hospital",
    "appointment": "hospital",
}


async def route_to(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    service = SERVICE_SYNONYMS.get(str(a.get("service", "")).lower().strip(), "")
    if service not in ("restaurant", "hospital"):
        return err("INVALID_ARGS", "service must be restaurant or hospital"), None
    s.ctx.service = service  # type: ignore[assignment]
    await s.emit("agent_switched", {"from": "router", "to": service})
    return {
        "ok": True,
        "service": service,
        "note": "Now continue as the " + service + " agent using what the caller already said.",
    }, service


ROUTER = NodeSpec(
    name="router",
    task=(
        "You are the front desk. Work out whether the caller wants a RESTAURANT table or a DOCTOR / HOSPITAL "
        "appointment and call route_to at once. Most callers say it in their first sentence. If it is truly unclear, "
        "ask ONE short question. Don't collect details here."
    ),
    functions=[
        FunctionSpec(
            "route_to",
            "Send the caller to the restaurant or hospital agent.",
            {"service": _str("restaurant | hospital", ["restaurant", "hospital"])},
            ["service"],
            route_to,
        ),
    ],
)


# ---------------------------------------------------------------------------
# Shared: FAQ, confirm
# ---------------------------------------------------------------------------


async def answer_faq(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    ref = str(a.get("business", ""))
    biz_id = None
    if r := find_restaurant(s, ref) if s.ctx.service != "hospital" else None:
        biz_id = r.restaurant_id
    elif h := find_hospital(s, ref):
        biz_id = h.hospital_id
    elif r2 := find_restaurant(s, ref):
        biz_id = r2.restaurant_id
    if not biz_id:
        return err("UNKNOWN_BUSINESS", f"No business called {ref!r}; ask which one"), None
    out = await run_tool(
        s.tools, "answer_faq", {"business_id": biz_id, "question": str(a.get("question", "")), "lang": s.ctx.language}
    )
    if out.get("answer"):
        s.ctx.faq_answered = True
        await s.set_slot("business_id", biz_id)
    return out, None


async def confirm_booking(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    p = s.ctx.pending
    if s.ctx.emergency:
        return err("EMERGENCY_CALL", "No bookings on an emergency call"), None
    if p is None:
        return err("NO_READBACK", "Call propose_booking / propose_appointment first and read it back"), None
    if p.turn >= s.ctx.turn:
        return err("WAIT_FOR_YES", "Read the details back and wait for the caller to say yes on their next turn"), None
    booked = await run_tool(s.tools, p.tool, p.args)
    if not booked.get("ok"):
        s.ctx.pending = None
        if booked.get("error") in ("SLOT_FULL", "SLOT_TAKEN", "BLOCKED"):
            s.ctx.offered_alternatives = True
        return booked, None
    s.ctx.booking_id = str(booked["booking_id"])
    s.ctx.pending = None
    sent = await run_tool(s.tools, "send_confirmation", {"booking_id": booked["booking_id"]})
    out: Result = {
        "ok": True,
        "booking_id": booked["booking_id"],
        "whatsapp": sent.get("status"),
        "deposit_inr": booked.get("deposit_inr") or 0,
        "fee_inr": booked.get("fee_inr") or 0,
        "note": (
            "Tell the caller the booking ID, that details are on WhatsApp (with a test-mode payment link "
            "if a deposit/fee is due), and ask if they need anything else."
        ),
    }
    return out, None


CONFIRM = FunctionSpec(
    "confirm_booking",
    "Book it. ONLY after you read the details back and the caller said yes on this turn.",
    {},
    [],
    confirm_booking,
)


# ---------------------------------------------------------------------------
# Restaurant agent
# ---------------------------------------------------------------------------


async def search_restaurants(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    area_id, problem = await resolve_area_words(s, a.get("area"))
    if problem:
        return problem, None
    d = caller_day(s) or resolve_date(s, a.get("date"))
    if d is None:
        return err("ASK_DATE", "Ask which day"), None
    party = s.ctx.slots.get("party_size") or a.get("party_size")  # caller's words (extracted) first
    if not party:
        return err("ASK_PARTY_SIZE", "Ask how many people"), None
    t = caller_time(s, "restaurant") or resolve_time(a.get("time"), "restaurant")
    args: dict[str, Any] = {"area_id": area_id, "party_size": int(party), "date": d.isoformat()}
    if t:
        args["time"] = t
    if a.get("cuisine"):
        args["cuisine"] = str(a["cuisine"])
    if a.get("food_type") in ("veg", "non-veg"):
        args["food_type"] = a["food_type"]
    r = await run_tool(s.tools, "search_restaurants", args)
    named = find_restaurant(s, None) if str(s.ctx.slots.get("business_id") or "").startswith("r_") else None
    if named and r.get("ok"):
        # The caller already named a restaurant: check it directly instead of steering them elsewhere.
        check_args: dict[str, Any] = {
            "restaurant_id": named.restaurant_id,
            "date": d.isoformat(),
            "party_size": int(party),
        }
        if t:
            check_args["time"] = t
        chk = await run_tool(s.tools, "get_restaurant_slots", check_args)
        lang = s.ctx.language
        if chk.get("ok"):
            r["named_restaurant"] = {
                "restaurant_id": named.restaurant_id,
                "name": named.name,
                "rating": named.rating,
                "free": spoken_list(chk.get("free", []), lang),
                "requested": spoken_time(t, lang) if t else None,
                "requested_free": (t in chk.get("free", [])) if t else None,
                "nearest": spoken_list(chk.get("nearest", []), lang),
            }
            if chk.get("requested_full"):
                s.ctx.offered_alternatives = True
                s.ctx.nearest_offered = list(chk.get("nearest", []))
        else:
            r["named_restaurant"] = {"restaurant_id": named.restaurant_id, "name": named.name, **chk}
            if chk.get("error") == "PARTY_TOO_LARGE":
                s.ctx.offered_alternatives = True
        r["note"] = "The caller named " + named.name + ": talk about named_restaurant first."
    if r.get("ok"):
        await s.set_slot("date", d.isoformat())
        await s.set_slot("party_size", int(party))
        s.ctx.search_result_ids += [x["restaurant_id"] for x in r["results"]]
        if not r["results"]:
            s.ctx.no_availability = True
        # Keep what the LLM sees short: 3 options, a few free times each.
        lang = s.ctx.language
        r["results"] = [{**x, "free_times": spoken_list(x["free_times"][:6], lang)} for x in r["results"]]
    return {**r, "date": d.isoformat(), "time": t}, None


async def get_slots(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    rest = find_restaurant(s, a.get("restaurant"))
    if rest is None:
        return err("UNKNOWN_BUSINESS", "Which restaurant? Use one from the search results"), None
    d = caller_day(s) or resolve_date(s, a.get("date"))
    party = s.ctx.slots.get("party_size") or a.get("party_size")
    if d is None or not party:
        return err("ASK_DETAILS", "Need the day and the number of people"), None
    t = caller_time(s, "restaurant") or resolve_time(a.get("time"), "restaurant")
    args: dict[str, Any] = {"restaurant_id": rest.restaurant_id, "date": d.isoformat(), "party_size": int(party)}
    if t:
        args["time"] = t
    r = await run_tool(s.tools, "get_restaurant_slots", args)
    await s.set_slot("business_id", rest.restaurant_id)
    if r.get("ok"):
        await s.set_slot("date", d.isoformat())
        await s.set_slot("party_size", int(party))
        if r.get("requested_full"):
            s.ctx.offered_alternatives = True
            s.ctx.nearest_offered = list(r.get("nearest", []))
        if not r.get("free"):
            s.ctx.no_availability = True
        lang = s.ctx.language
        raw_free = list(r.get("free", []))
        r = {**r, "free": spoken_list(raw_free, lang), "nearest": spoken_list(r.get("nearest", []), lang)}
        if t:
            r["requested"] = spoken_time(t, lang)
            r["requested_free"] = t in raw_free
    elif r.get("error") == "PARTY_TOO_LARGE":
        s.ctx.offered_alternatives = True
    return {**r, "restaurant": rest.name, "note": "Say times exactly as given (spoken form)."}, None


async def propose_booking(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    if s.ctx.emergency:
        return err("EMERGENCY_CALL", "No bookings on an emergency call"), None
    rest = find_restaurant(s, a.get("restaurant"))
    # Code decides: a day/time in the caller's latest words beats the LLM's argument.
    d = caller_day(s) or resolve_date(s, a.get("date"))
    t = caller_time(s, "restaurant") or resolve_time(a.get("time"), "restaurant") or s.ctx.slots.get("time")
    party = s.ctx.slots.get("party_size") or a.get("party_size")
    name = caller_name(s, a.get("name"))
    missing = [
        k for k, v in {"restaurant": rest, "date": d, "time": t, "party_size": party, "name": name}.items() if not v
    ]
    if missing:
        return err("MISSING_DETAILS", "Ask for: " + ", ".join(missing), missing=missing), None
    assert rest and d and t and party
    party = int(party)
    check = await run_tool(
        s.tools,
        "get_restaurant_slots",
        {"restaurant_id": rest.restaurant_id, "date": d.isoformat(), "party_size": int(party), "time": t},
    )
    if not check.get("ok"):
        if check.get("error") == "PARTY_TOO_LARGE":
            s.ctx.offered_alternatives = True
        return check, None
    if check.get("requested_full"):
        s.ctx.offered_alternatives = True
        s.ctx.nearest_offered = list(check.get("nearest", []))
        return err(
            "SLOT_FULL",
            f"{spoken_time(t, s.ctx.language)} is full",
            nearest=spoken_list(check.get("nearest", []), s.ctx.language),
        ), None
    for k, v in (
        ("business_id", rest.restaurant_id),
        ("date", d.isoformat()),
        ("time", t),
        ("party_size", int(party)),
        ("name", name),
    ):
        await s.set_slot(k, v)
    rules = rest.booking_rules
    deposit = rules.deposit_inr if int(party) >= rules.deposit_required_for_party_size_at_least else 0
    readback = {
        "restaurant": rest.name,
        "date": d.isoformat(),
        "day": s.day_words(d),
        "time": t,
        "party_size": int(party),
        "name": name,
        "deposit_inr": deposit,
    }
    s.ctx.pending = Pending(
        "restaurant",
        "book_table",
        {"restaurant_id": rest.restaurant_id, "date": d.isoformat(), "time": t, "party_size": int(party), "name": name},
        readback,
        s.ctx.turn,
    )
    say = restaurant_readback(
        s.ctx.language, business=rest.name, d=d, time=t, party=int(party), name=name, deposit=deposit
    )
    return {"ok": True, "readback": readback, "force_say": say}, None


RESTAURANT = NodeSpec(
    name="restaurant",
    task=(
        "You book restaurant tables. Collect only what's missing, one thing at a time: area (Jubilee Hills or "
        "Gachibowli), day, number of people, then let the caller choose from at most 3 options, a time, and "
        "their name. "
        "Pass the caller's own words for area/day/time; code resolves them. Steps: search_restaurants → read the top 3 "
        "(name, rating, one detail) → get_slots for the chosen one (if the time is full, offer the 2 nearest) → "
        "propose_booking → read back once → after the caller's yes on their next turn, confirm_booking → booking ID + "
        "WhatsApp + 'anything else?'. Questions about parking, timings, veg, kids, deposits → answer_faq. Never invent "
        "names, ratings, times or IDs: use only tool results."
    ),
    functions=[
        FunctionSpec(
            "search_restaurants",
            "Top 3 restaurants with a free table.",
            {
                "area": _str("area words, e.g. 'Jubilee Hills'"),
                "date": _str("day words or YYYY-MM-DD, e.g. 'kal', 'repu', 'tomorrow'"),
                "party_size": _int("people"),
                "time": _str("optional time words, e.g. '8:30', 'saadhe aath'"),
                "cuisine": _str("optional, e.g. biryani, seafood"),
                "food_type": _str("optional", ["veg", "non-veg"]),
            },
            ["area", "date", "party_size"],
            search_restaurants,
        ),
        FunctionSpec(
            "get_slots",
            "Free times at one restaurant (2 nearest if the asked time is full).",
            {
                "restaurant": _str("restaurant_id or name"),
                "date": _str("day words or YYYY-MM-DD"),
                "party_size": _int("people"),
                "time": _str("optional time words"),
            },
            ["restaurant"],
            get_slots,
        ),
        FunctionSpec(
            "propose_booking",
            "Check the slot and prepare the read-back. Does NOT book.",
            {
                "restaurant": _str("restaurant_id or name"),
                "date": _str("day words or YYYY-MM-DD"),
                "time": _str("time words or HH:MM"),
                "party_size": _int("people"),
                "name": _str("caller's name"),
            },
            ["restaurant", "date", "time", "party_size", "name"],
            propose_booking,
        ),
        CONFIRM,
        FunctionSpec(
            "answer_faq",
            "Answer a question about one restaurant from its FAQs.",
            {"business": _str("restaurant_id or name"), "question": _str("the caller's question")},
            ["business", "question"],
            answer_faq,
        ),
    ],
)


# ---------------------------------------------------------------------------
# Hospital agent
# ---------------------------------------------------------------------------


async def map_need(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    r = await run_tool(s.tools, "map_speciality", {"text": str(a.get("text", "")), "lang": s.ctx.language})
    if r.get("emergency"):
        s.ctx.emergency = True
        s.ctx.pending = None
        return {**r, "say_this": r["reply"], "note": "Say only this. Do not book."}, None
    if r.get("speciality"):
        await s.set_slot("speciality", r["speciality"])
    return r, None


async def search_hospitals(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    area_id, problem = await resolve_area_words(s, a.get("area"))
    if problem:
        return problem, None
    spec = str(a.get("speciality") or s.ctx.slots.get("speciality") or "")
    if spec not in SPECIALITIES:
        mapped = await run_tool(s.tools, "map_speciality", {"text": spec, "lang": s.ctx.language}) if spec else {}
        if mapped.get("emergency"):
            s.ctx.emergency = True
            return {**mapped, "say_this": mapped["reply"]}, None
        spec = str(mapped.get("speciality") or "")
    if not spec:
        return err("ASK_NEED", "Ask what the problem is or which doctor they need"), None
    await s.set_slot("speciality", spec)
    d = caller_day(s) or resolve_date(s, a.get("date"))
    args: dict[str, Any] = {"area_id": area_id, "speciality": spec}
    if d:
        args["date"] = d.isoformat()
    r = await run_tool(s.tools, "search_hospitals", args)
    # The caller named a doctor ("Dr. Kavya Sharma garu"): show that doctor's own availability too.
    named = named_doctor(s, spec)
    if named and r.get("ok"):
        slots = await run_tool(
            s.tools, "get_doctor_slots", {"doctor_id": named.doctor_id, "date": (d or today_ist()).isoformat()}
        )
        r["named_doctor"] = {
            "doctor_id": named.doctor_id,
            "name": named.name,
            "on_leave": slots.get("on_leave"),
            "fully_booked": slots.get("fully_booked"),
            "free": spoken_list(slots.get("free", [])[:6], s.ctx.language),
            "next_free_date": slots.get("next_free_date"),
        }
        await s.set_slot("doctor_id", named.doctor_id)
        await s.set_slot("business_id", named.hospital_id)
        if slots.get("on_leave") or slots.get("fully_booked"):
            s.ctx.offered_alternatives = True
    if r.get("ok"):
        s.ctx.search_result_ids += [x["hospital_id"] for x in r["results"]]
        for x in r["results"]:
            x["next_free"]["time"] = spoken_time(x["next_free"]["time"], s.ctx.language)
        if d:
            await s.set_slot("date", d.isoformat())
        if not r["results"]:
            s.ctx.no_availability = True
    return r, None


def named_doctor(s: Session, speciality: str | None = None) -> Doctor | None:
    """A doctor the caller named in their latest message, if any."""
    text = s.last_caller_text().lower()
    if "dr" not in text and "doctor" not in text:
        return None
    for d in s.catalog.doctors:
        if speciality and d.speciality != speciality:
            continue
        first, *rest = d.name.replace("Dr. ", "").lower().split()
        if first in text and (not rest or rest[-1] in text or f"dr {first}" in text.replace(".", "")):
            return d
    return None


async def get_doctor_slots(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    doc = find_doctor(s, a.get("doctor"))
    if doc is None:
        return err("UNKNOWN_DOCTOR", "Which doctor? Use one from the search results"), None
    d = caller_day(s) or resolve_date(s, a.get("date"))
    if d is None:
        return err("ASK_DATE", "Ask which day"), None
    r = await run_tool(s.tools, "get_doctor_slots", {"doctor_id": doc.doctor_id, "date": d.isoformat()})
    await s.set_slot("doctor_id", doc.doctor_id)
    await s.set_slot("business_id", doc.hospital_id)
    await s.set_slot("speciality", doc.speciality)
    if r.get("ok"):
        await s.set_slot("date", d.isoformat())
        if r.get("on_leave") or r.get("fully_booked"):
            s.ctx.offered_alternatives = True
        # Long free lists → first 8 + count (the agent reads a few, not all).
        free = r.get("free", [])
        want = caller_time(s, "hospital")
        r = {**r, "free": spoken_list(free[:8], s.ctx.language), "free_count": len(free)}
        if want:
            r["requested"] = spoken_time(want, s.ctx.language)
            r["requested_free"] = want in free
    return {**r, "doctor": doc.name}, None


async def propose_appointment(s: Session, a: dict[str, Any]) -> tuple[Result, str | None]:
    if s.ctx.emergency:
        return err("EMERGENCY_CALL", "No bookings on an emergency call"), None
    doc = find_doctor(s, a.get("doctor"))
    d = caller_day(s) or resolve_date(s, a.get("date"))
    t = caller_time(s, "hospital") or resolve_time(a.get("time"), "hospital") or s.ctx.slots.get("time")
    name = caller_name(s, a.get("name"))
    missing = [k for k, v in {"doctor": doc, "date": d, "time": t, "name": name}.items() if not v]
    if missing:
        return err("MISSING_DETAILS", "Ask for: " + ", ".join(missing), missing=missing), None
    assert doc and d and t
    check = await run_tool(s.tools, "get_doctor_slots", {"doctor_id": doc.doctor_id, "date": d.isoformat()})
    if not check.get("ok"):
        return check, None
    if t not in check.get("free", []):
        s.ctx.offered_alternatives = True
        free = check.get("free", [])
        lang = s.ctx.language
        return err(
            "SLOT_TAKEN",
            f"{spoken_time(t, lang)} is not free",
            free=spoken_list(free[:6], lang),
            on_leave=check.get("on_leave"),
            next_free_date=check.get("next_free_date"),
        ), None
    hosp = next(h for h in s.catalog.hospitals if h.hospital_id == doc.hospital_id)
    for k, v in (
        ("business_id", hosp.hospital_id),
        ("doctor_id", doc.doctor_id),
        ("speciality", doc.speciality),
        ("date", d.isoformat()),
        ("time", t),
        ("name", name),
    ):
        await s.set_slot(k, v)
    readback = {
        "hospital": hosp.name,
        "doctor": doc.name,
        "speciality": doc.speciality,
        "date": d.isoformat(),
        "day": s.day_words(d),
        "time": t,
        "name": name,
        "fee_inr": doc.consultation_fee_inr,
    }
    s.ctx.pending = Pending(
        "hospital",
        "book_appointment",
        {"doctor_id": doc.doctor_id, "date": d.isoformat(), "time": t, "name": name},
        readback,
        s.ctx.turn,
    )
    say = appointment_readback(
        s.ctx.language, hospital=hosp.name, doctor=doc.name, d=d, time=t, name=name, fee=doc.consultation_fee_inr
    )
    return {"ok": True, "readback": readback, "force_say": say}, None


HOSPITAL = NodeSpec(
    name="hospital",
    task=(
        "You book doctor appointments. Never diagnose or give medical advice. If the caller names a doctor, use that "
        "doctor (get_doctor_slots / named_doctor in results) instead of suggesting others first. "
        "Collect what's missing, one thing at a "
        "time: area (Jubilee Hills or Gachibowli), the need in the caller's words (map_need turns it into a "
        "speciality; emergencies are handled for you), day, then a doctor from at most 3 options, a time, and the "
        "caller's name. Steps: map_need → search_hospitals → read the top 3 (hospital, rating, doctor, next free "
        "time) → get_doctor_slots for the chosen doctor (if on leave or full, offer the next free day or another "
        "doctor) → propose_appointment → read back once (with the fee) → after the caller's yes on their next turn, "
        "confirm_booking → booking ID + WhatsApp (fee payment link) + 'anything else?'. Questions about insurance, "
        "timings, parking, emergency → answer_faq. Never invent names, times or IDs."
    ),
    functions=[
        FunctionSpec(
            "map_need",
            "Caller's words about the problem → speciality (or emergency).",
            {"text": _str("the caller's words, e.g. 'skin doctor', 'pallu noppi'")},
            ["text"],
            map_need,
        ),
        FunctionSpec(
            "search_hospitals",
            "Top 3 hospitals with a doctor of that speciality and their next free slot.",
            {
                "area": _str("area words"),
                "speciality": _str("speciality from map_need, or the caller's words"),
                "date": _str("optional day words or YYYY-MM-DD"),
            },
            ["area", "speciality"],
            search_hospitals,
        ),
        FunctionSpec(
            "get_doctor_slots",
            "Free times for one doctor on a day.",
            {"doctor": _str("doctor_id or name"), "date": _str("day words or YYYY-MM-DD")},
            ["doctor", "date"],
            get_doctor_slots,
        ),
        FunctionSpec(
            "propose_appointment",
            "Check the slot and prepare the read-back. Does NOT book.",
            {
                "doctor": _str("doctor_id or name"),
                "date": _str("day words or YYYY-MM-DD"),
                "time": _str("time words or HH:MM"),
                "name": _str("caller's name"),
            },
            ["doctor", "date", "time", "name"],
            propose_appointment,
        ),
        CONFIRM,
        FunctionSpec(
            "answer_faq",
            "Answer a question about one hospital from its FAQs.",
            {"business": _str("hospital_id or name"), "question": _str("the caller's question")},
            ["business", "question"],
            answer_faq,
        ),
    ],
)

NODES: dict[str, NodeSpec] = {n.name: n for n in (ROUTER, RESTAURANT, HOSPITAL)}


def functions_for(node: str) -> dict[str, FunctionSpec]:
    return {f.name: f for f in [*NODES[node].functions, *GLOBAL_FUNCTIONS]}
