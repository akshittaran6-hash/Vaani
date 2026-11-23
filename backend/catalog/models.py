"""Pydantic models for the 9 data files in data/ (contract: docs/CONTRACTS.md §7).

These models check *shape* (fields, types, enums, HH:MM format). Cross-file rules
(IDs exist, 5+5 per area, times inside schedules, …) live in validate.py.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

DAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
LANGS: tuple[str, ...] = ("te", "hi", "en")
LANGUAGE_MIXES: tuple[str, ...] = ("te-en", "hi-en", "en-IN")

SPECIALITIES: tuple[str, ...] = (
    "General Medicine",
    "Dermatology",
    "Gynecology",
    "Pediatrics",
    "Orthopedics",
    "ENT",
    "Cardiology",
    "Dental",
    "Ophthalmology",
)

# Fixed bookable start times for restaurants (CONTRACTS.md §1 restaurant_slots).
LUNCH_TIMES: tuple[str, ...] = ("12:30", "13:00", "13:30", "14:00")
DINNER_TIMES: tuple[str, ...] = ("19:00", "19:30", "20:00", "20:30", "21:00", "21:30")
BOOKABLE_TIMES: tuple[str, ...] = LUNCH_TIMES + DINNER_TIMES

SCENARIOS: tuple[str, ...] = (
    "happy_path",
    "unsupported_area",
    "slot_full",
    "mid_call_change",
    "vague_request",
    "party_limit",
    "deposit_needed",
    "doctor_fully_booked",
    "doctor_on_leave",
    "emergency",
    "faq",
)

PHRASE_KEYS: tuple[str, ...] = (
    "greeting_with_ai_disclosure",
    "ask_area",
    "ask_date_time",
    "ask_party_size",
    "ask_name",
    "reading_top3_intro",
    "slot_full_offer_alternatives",
    "confirm_booking_readback",
    "booking_done_whatsapp_sent",
    "filler_checking",
    "didnt_catch_that",
    "silence_check",
    "anything_else",
    "goodbye",
    "unsupported_area",
    "emergency_redirect",
    "transfer_to_human",
    "never_ask_otp",
)

# ---------------------------------------------------------------------------
# Field types
# ---------------------------------------------------------------------------

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_RANGE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-4]):[0-5]\d$")


def _check_hhmm(v: str) -> str:
    if not _HHMM.match(v):
        raise ValueError(f"time must be 24h HH:MM, got {v!r}")
    return v


def _check_range(v: str) -> str:
    if not _RANGE.match(v):
        raise ValueError(f"range must be 'HH:MM-HH:MM', got {v!r}")
    start, end = v.split("-")
    if to_minutes(start) >= to_minutes(end):
        raise ValueError(f"range must end after it starts, got {v!r}")
    return v


def _check_hex(v: str) -> str:
    if not re.match(r"^#[0-9A-Fa-f]{6}$", v):
        raise ValueError(f"accent_color must be #RRGGBB, got {v!r}")
    return v


HHMM = Annotated[str, AfterValidator(_check_hhmm)]
TimeRange = Annotated[str, AfterValidator(_check_range)]
HexColor = Annotated[str, AfterValidator(_check_hex)]
DayOffset = Annotated[int, Field(ge=0, le=6)]
Rating = Annotated[float, Field(ge=0, le=5)]
NonEmpty = Annotated[str, Field(min_length=1)]


def to_minutes(hhmm: str) -> int:
    """'20:30' -> 1230. Accepts '24:00' as end of day."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def from_minutes(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def parse_range(r: str) -> tuple[int, int]:
    start, end = r.split("-")
    return to_minutes(start), to_minutes(end)


class Strict(BaseModel):
    """Unknown fields are errors, so typos in ChatGPT output are caught."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------------------
# File models
# ---------------------------------------------------------------------------


class LocalizedText(Strict):
    te: NonEmpty
    hi: NonEmpty
    en: NonEmpty


class Faq(Strict):
    q: NonEmpty
    a_en: NonEmpty
    a_te: NonEmpty
    a_hi: NonEmpty


class Area(Strict):
    area_id: NonEmpty
    name_en: NonEmpty
    name_te: NonEmpty
    name_hi: NonEmpty
    aliases: list[NonEmpty]
    lat: float
    lng: float
    nearby_unsupported_areas: list[NonEmpty]
    unsupported_area_reply: LocalizedText
    is_sample_data: bool


class RestaurantFeatures(Strict):
    parking: bool
    outdoor_seating: bool
    kids_friendly: bool
    wheelchair_access: bool
    live_music: bool


class BookingRules(Strict):
    max_party_size: Annotated[int, Field(ge=1)]
    deposit_required_for_party_size_at_least: Annotated[int, Field(ge=1)]
    deposit_inr: Annotated[int, Field(ge=0)]
    cancellation: NonEmpty


class Table(Strict):
    table_id: Annotated[str, Field(pattern=r"^T\d+$")]
    capacity: Annotated[int, Field(ge=1, le=20)]


class Restaurant(Strict):
    restaurant_id: Annotated[str, Field(pattern=r"^r_[a-z]+_\d{2}$")]
    slug: Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
    name: NonEmpty
    name_spoken_te: NonEmpty
    name_spoken_hi: NonEmpty
    name_aliases: list[NonEmpty]
    area_id: NonEmpty
    address: NonEmpty
    cuisines: Annotated[list[NonEmpty], Field(min_length=1)]
    food_type: Literal["veg", "non-veg", "both"]
    rating: Rating
    price_for_two_inr: Annotated[int, Field(gt=0)]
    highlight: NonEmpty
    popular_dishes: Annotated[list[NonEmpty], Field(min_length=3, max_length=5)]
    opening_hours: dict[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"], list[TimeRange]]
    features: RestaurantFeatures
    booking_rules: BookingRules
    tables: Annotated[list[Table], Field(min_length=1)]
    slot_length_minutes: Annotated[int, Field(ge=15, le=240)]
    accent_color: HexColor
    faqs: list[Faq]
    phone: Annotated[str, Field(pattern=r"^DEMO-R-\d{3}$")]
    is_sample_data: bool


class RestaurantSlotException(Strict):
    restaurant_id: NonEmpty
    day_offset: DayOffset
    time: HHMM
    booked_table_ids: list[NonEmpty]
    blocked: bool = False


class HospitalFacilities(Strict):
    emergency_24x7: bool
    pharmacy: bool
    lab: bool
    ambulance: bool
    cashless_insurance: bool
    wheelchair_access: bool


Speciality = Literal[
    "General Medicine",
    "Dermatology",
    "Gynecology",
    "Pediatrics",
    "Orthopedics",
    "ENT",
    "Cardiology",
    "Dental",
    "Ophthalmology",
]


class Hospital(Strict):
    hospital_id: Annotated[str, Field(pattern=r"^h_[a-z]+_\d{2}$")]
    slug: Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
    name: NonEmpty
    name_spoken_te: NonEmpty
    name_spoken_hi: NonEmpty
    name_aliases: list[NonEmpty]
    area_id: NonEmpty
    type: Literal["multi-speciality hospital", "clinic"]
    address: NonEmpty
    rating: Rating
    highlight: NonEmpty
    specialities: Annotated[list[Speciality], Field(min_length=1)]
    facilities: HospitalFacilities
    # "" = closed that day
    opd_hours: dict[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"], str]
    languages_spoken: list[NonEmpty]
    accent_color: HexColor
    faqs: list[Faq]
    phone: Annotated[str, Field(pattern=r"^DEMO-H-\d{3}$")]
    is_sample_data: bool


class Doctor(Strict):
    doctor_id: Annotated[str, Field(pattern=r"^d_[a-z]+_\d{2}_[a-z]+_\d+$")]
    hospital_id: NonEmpty
    name: Annotated[str, Field(pattern=r"^Dr\. .+")]
    name_spoken_te: NonEmpty
    name_spoken_hi: NonEmpty
    gender: Literal["female", "male"]
    speciality: Speciality
    qualification: NonEmpty
    experience_years: Annotated[int, Field(ge=0, le=60)]
    languages: Annotated[list[NonEmpty], Field(min_length=1)]
    consultation_fee_inr: Annotated[int, Field(ge=0)]
    # Only the days the doctor works; one range per day.
    schedule: dict[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"], TimeRange]
    slot_length_minutes: Annotated[int, Field(ge=5, le=60)]
    on_leave_day_offsets: list[DayOffset] = Field(default_factory=list)
    is_sample_data: bool


class DoctorSlotException(Strict):
    doctor_id: NonEmpty
    day_offset: DayOffset
    booked_times: list[HHMM]
    blocked_times: list[HHMM] = Field(default_factory=list)


class SpecialityPhrase(Strict):
    phrase: NonEmpty
    lang: Literal["te", "hi", "en"]
    speciality: Speciality


class EmergencyPhrase(Strict):
    phrase: NonEmpty
    lang: Literal["te", "hi", "en"]


class SpecialityMapping(Strict):
    phrases: list[SpecialityPhrase]
    emergency_phrases: list[EmergencyPhrase]
    emergency_reply: LocalizedText
    # Self-harm / suicidal thoughts: a separate, gentle reply with the Tele-MANAS helpline
    # (14416 / 1-800-891-4416) and 112 for immediate danger. Checked before emergencies.
    self_harm_phrases: list[EmergencyPhrase] = Field(default_factory=list)
    self_harm_reply: LocalizedText | None = None


class TestCallExpected(Strict):
    __test__ = False  # not a pytest test class
    intent: Literal["book", "info", "unsupported_area", "emergency"]
    area_id: str | None
    business_id: str | None
    speciality: Speciality | None
    doctor_id: str | None
    day_offset: DayOffset | None
    time: HHMM | None
    party_size: Annotated[int, Field(ge=1)] | None
    outcome: Literal[
        "booked",
        "offered_alternatives",
        "declined_unsupported_area",
        "redirected_emergency",
        "answered_faq",
        "no_availability",
    ]


class TestCall(Strict):
    __test__ = False  # not a pytest test class
    test_id: Annotated[str, Field(pattern=r"^T\d{2}$")]
    service: Literal["restaurant", "hospital"]
    language_mix: Literal["te-en", "hi-en", "en-IN"]
    scenario: Literal[
        "happy_path",
        "unsupported_area",
        "slot_full",
        "mid_call_change",
        "vague_request",
        "party_limit",
        "deposit_needed",
        "doctor_fully_booked",
        "doctor_on_leave",
        "emergency",
        "faq",
    ]
    caller_turns: Annotated[list[NonEmpty], Field(min_length=1)]
    expected: TestCallExpected


class AgentPhrase(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    key: NonEmpty
    te_en: Annotated[list[NonEmpty], Field(alias="te-en")]
    hi_en: Annotated[list[NonEmpty], Field(alias="hi-en")]
    en_in: Annotated[list[NonEmpty], Field(alias="en-IN")]


class Catalog(BaseModel):
    """All 9 files, parsed."""

    model_config = ConfigDict(frozen=True)

    areas: list[Area]
    restaurants: list[Restaurant]
    restaurant_availability: list[RestaurantSlotException]
    hospitals: list[Hospital]
    doctors: list[Doctor]
    doctor_availability: list[DoctorSlotException]
    speciality_mapping: SpecialityMapping
    test_calls: list[TestCall]
    agent_phrases: list[AgentPhrase]
