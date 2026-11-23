"""Restaurant tools: search_restaurants, get_restaurant_slots, book_table."""

from __future__ import annotations

import datetime as dt
from datetime import date, time
from typing import Any, Literal

import psycopg
from pydantic import Field

from backend.catalog.models import Restaurant
from backend.clock import is_past
from backend.text import norm
from backend.tools.base import Args, Result, ToolContext, ToolError, day_word, require_area, require_window, tool

MAX_RESULTS = 3  # never read more than 3 options aloud (CLAUDE.md rule 2)

SLOTS_SQL = """
select s.restaurant_id, s.time, s.blocked,
       count(t.table_id) filter (where not t.table_id = any (s.booked_table_ids)) as free_tables,
       count(t.table_id) as total_tables,
       count(t.table_id) filter (
         where not t.table_id = any (s.booked_table_ids) and t.capacity >= %(party)s) as fitting
  from public.restaurant_slots s
  join public.restaurant_tables t on t.restaurant_id = s.restaurant_id
 where s.restaurant_id = any (%(ids)s) and s.date = %(date)s
 group by s.restaurant_id, s.time, s.blocked
 order by s.restaurant_id, s.time
"""


def restaurant(ctx: ToolContext, restaurant_id: str) -> Restaurant:
    r = next((x for x in ctx.catalog.restaurants if x.restaurant_id == restaurant_id), None)
    if r is None:
        raise ToolError("UNKNOWN_BUSINESS", f"No restaurant {restaurant_id}")
    return r


def hhmm(t: time) -> str:
    return t.strftime("%H:%M")


async def slot_rows(ctx: ToolContext, ids: list[str], d: date, party: int) -> list[dict[str, Any]]:
    return await ctx.store.fetch(SLOTS_SQL, {"ids": ids, "date": d, "party": party})


def free_times(rows: list[dict[str, Any]], d: date) -> list[str]:
    """Bookable for this party: not blocked, a fitting table free, not already past."""
    return [hhmm(r["time"]) for r in rows if not r["blocked"] and r["fitting"] > 0 and not is_past(d, r["time"])]


def nearest(free: list[str], requested: str, n: int = 2) -> list[str]:
    def minutes(t: str) -> int:
        return int(t[:2]) * 60 + int(t[3:])

    picked = sorted(free, key=lambda t: (abs(minutes(t) - minutes(requested)), minutes(t)))[:n]
    return sorted(picked, key=minutes)


def check_party(r: Restaurant, party: int) -> None:
    if party > r.booking_rules.max_party_size:
        raise ToolError(
            "PARTY_TOO_LARGE",
            f"{r.name} seats at most {r.booking_rules.max_party_size} per booking",
            max_party_size=r.booking_rules.max_party_size,
        )


# ---------------------------------------------------------------------------


class SearchRestaurantsArgs(Args):
    area_id: str
    party_size: int = Field(ge=1, le=50)
    date: dt.date
    time: dt.time | None = None
    cuisine: str | None = None
    food_type: Literal["veg", "non-veg"] | None = None


@tool("search_restaurants", SearchRestaurantsArgs, "Top 3 restaurants in an area with a table free for the party.")
async def search_restaurants(ctx: ToolContext, a: SearchRestaurantsArgs) -> tuple[Result, str]:
    area_name = require_area(ctx, a.area_id)
    require_window(a.date)
    candidates = [r for r in ctx.catalog.restaurants if r.area_id == a.area_id]
    if a.food_type == "veg":
        candidates = [r for r in candidates if r.food_type in ("veg", "both")]
    elif a.food_type == "non-veg":
        candidates = [r for r in candidates if r.food_type in ("non-veg", "both")]
    if a.cuisine:
        want = norm(a.cuisine)
        candidates = [
            r
            for r in candidates
            if any(want in norm(c) or norm(c) in want for c in r.cuisines)
            or any(want in norm(d) for d in r.popular_dishes)
            or want in norm(r.highlight)
        ]
    too_small = [r for r in candidates if a.party_size > r.booking_rules.max_party_size]
    candidates = [r for r in candidates if a.party_size <= r.booking_rules.max_party_size]

    rows = await slot_rows(ctx, [r.restaurant_id for r in candidates], a.date, a.party_size)
    by_rest: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_rest.setdefault(row["restaurant_id"], []).append(row)

    results = []
    want_time = hhmm(a.time) if a.time else None
    for r in sorted(candidates, key=lambda x: -x.rating):
        free = free_times(by_rest.get(r.restaurant_id, []), a.date)
        if not free or (want_time and want_time not in free):
            continue
        results.append(
            {
                "restaurant_id": r.restaurant_id,
                "name": r.name,
                "rating": r.rating,
                "highlight": r.highlight,
                "cuisines": r.cuisines,
                "food_type": r.food_type,
                "free_times": free,
            }
        )
        if len(results) == MAX_RESULTS:
            break

    when = f"{a.party_size} people, {day_word(a.date)}" + (f" {want_time}" if want_time else "")
    out: Result = {"results": results}
    if not results:
        out["reason"] = "party_too_large" if too_small and not candidates else "no_availability"
    return (
        out,
        f"Searched restaurants → {len(results)} match{'es' if len(results) != 1 else ''} in {area_name} ({when})",
    )


class RestaurantSlotsArgs(Args):
    restaurant_id: str
    date: dt.date
    party_size: int = Field(ge=1, le=50)
    time: dt.time | None = None


@tool("get_restaurant_slots", RestaurantSlotsArgs, "Free start times; the 2 nearest when the requested time is full.")
async def get_restaurant_slots(ctx: ToolContext, a: RestaurantSlotsArgs) -> tuple[Result, str]:
    r = restaurant(ctx, a.restaurant_id)
    require_window(a.date)
    check_party(r, a.party_size)
    free = free_times(await slot_rows(ctx, [r.restaurant_id], a.date, a.party_size), a.date)
    out: Result = {"restaurant_id": r.restaurant_id, "date": a.date.isoformat(), "free": free}
    summary = f"Checked {r.name} slots → {', '.join(free[:4]) or 'none'} free"
    if a.time:
        req = hhmm(a.time)
        out["requested"] = req
        out["requested_full"] = req not in free
        if req not in free:
            out["nearest"] = nearest(free, req)
            summary = f"Checked {r.name} slots → {req} full, offered {', '.join(out['nearest']) or 'nothing'}"
    return out, summary


class BookTableArgs(Args):
    restaurant_id: str
    date: dt.date
    time: dt.time
    party_size: int = Field(ge=1, le=50)
    name: str = Field(min_length=1, max_length=80)
    phone: str | None = None  # filled from caller ID by the runner's context


@tool("book_table", BookTableArgs, "Book a table (only after the caller confirmed the read-back).")
async def book_table(ctx: ToolContext, a: BookTableArgs) -> tuple[Result, str]:
    r = restaurant(ctx, a.restaurant_id)
    require_window(a.date)
    check_party(r, a.party_size)
    phone = a.phone or ctx.phone
    if not phone:
        raise ToolError("MISSING_DETAILS", "No phone number for this call")
    try:
        row = await ctx.store.fetchrow(
            "select * from public.book_table(%(r)s, %(d)s, %(t)s, %(p)s, %(n)s, %(ph)s, %(lang)s, %(src)s, %(call)s)",
            {
                "r": r.restaurant_id,
                "d": a.date,
                "t": a.time,
                "p": a.party_size,
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
    out = {
        "booking_id": row["booking_id"],
        "table_id": row["table_id"],
        "deposit_needed": row["deposit_needed"],
        "deposit_inr": row["deposit_inr"],
    }
    if ctx.call_id:
        await ctx.emit(
            "booking_created",
            {
                "booking_id": row["booking_id"],
                "service": "restaurant",
                "business_id": r.restaurant_id,
                "date": a.date.isoformat(),
                "time": hhmm(a.time),
                "party_size": a.party_size,
                "table_id": row["table_id"],
                "language": ctx.language,
            },
        )
    return out, f"Booked table {row['table_id']} · {hhmm(a.time)} · ID {row['booking_id']}"


def db_error(e: psycopg.errors.RaiseException) -> ToolError:
    """Postgres booking functions raise message=<CODE>, hint=<explanation>."""
    return ToolError(str(e.diag.message_primary), str(e.diag.message_hint or e.diag.message_primary))
