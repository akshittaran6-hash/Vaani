"""Turns opening hours and doctor schedules into concrete slot times.

Shared by validate.py, seeding.py and (from Phase 2) the tools, so every part of the
system agrees on which times exist.
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.catalog.models import (
    BOOKABLE_TIMES,
    DAYS,
    Doctor,
    Hospital,
    Restaurant,
    from_minutes,
    parse_range,
    to_minutes,
)


def day_key(d: date) -> str:
    """date -> 'mon' … 'sun'."""
    return DAYS[d.weekday()]


def offset_to_date(today: date, day_offset: int) -> date:
    return today + timedelta(days=day_offset)


def restaurant_times(restaurant: Restaurant, day: str) -> list[str]:
    """Bookable start times on a weekday: the fixed lunch/dinner list, kept only when the
    start falls inside an opening range (open <= start < close)."""
    ranges = [parse_range(r) for r in restaurant.opening_hours.get(day, [])]  # type: ignore[call-overload]
    return [t for t in BOOKABLE_TIMES if any(lo <= to_minutes(t) < hi for lo, hi in ranges)]


def doctor_times(doctor: Doctor, day: str) -> list[str]:
    """Slot start times on a weekday: every slot_length step that ends by the range end."""
    rng = doctor.schedule.get(day)  # type: ignore[call-overload]
    if not rng:
        return []
    lo, hi = parse_range(rng)
    step = doctor.slot_length_minutes
    return [from_minutes(m) for m in range(lo, hi - step + 1, step)]


def works_every_day(doctor: Doctor) -> bool:
    return all(doctor.schedule.get(d) for d in DAYS)  # type: ignore[call-overload]


def every_day_times(doctor: Doctor) -> list[str]:
    """Slot times that exist on *every* weekday (hours may differ per weekday, e.g. a later
    close on Saturday). A day_offset lands on a different weekday depending on the seed date,
    so availability exceptions and test-call times must use only these. [] if a day is off."""
    if not works_every_day(doctor):
        return []
    common = set(doctor_times(doctor, DAYS[0]))
    for d in DAYS[1:]:
        common &= set(doctor_times(doctor, d))
    return sorted(common)


def opd_range(hospital: Hospital, day: str) -> tuple[int, int] | None:
    """OPD hours as minutes, or None when closed ('' or missing)."""
    value = hospital.opd_hours.get(day, "")  # type: ignore[call-overload]
    if not value:
        return None
    return parse_range(value)
