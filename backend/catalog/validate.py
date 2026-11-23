"""Cross-file rules for data/ (docs/CONTRACTS.md §7, docs/DATA_PROMPT.md "FINAL CHECK").

Errors make validate_data.py exit 1 and block seeding. Warnings are things the data
prompt asks for that won't break the app (e.g. ratings repeated within an area).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from backend.catalog.models import (
    BOOKABLE_TIMES,
    DAYS,
    PHRASE_KEYS,
    SCENARIOS,
    SPECIALITIES,
    Catalog,
    Doctor,
    SpecialityMapping,
    parse_range,
)
from backend.catalog.schedule import (
    every_day_times,
    opd_range,
    restaurant_times,
    works_every_day,
)

PER_AREA = 5
# The greeting must name Vaani: Latin, Telugu or Devanagari spelling.
VAANI_SPELLINGS = ("Vaani", "వాణి", "वाणी")
MIN_PHRASES = 60
MIN_EMERGENCY = 30
TEST_CALLS = 40
# Target split of the 40 test calls (DATA_PROMPT: ~40% / 35% / 25%), with slack.
LANG_SPLIT = {"te-en": (14, 18), "hi-en": (12, 16), "en-IN": (8, 12)}


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _dupes(values: list[str]) -> list[str]:
    return sorted(v for v, n in Counter(values).items() if n > 1)


def validate_catalog(cat: Catalog) -> Report:
    r = Report()
    _check_sample_flags(cat, r)
    _check_areas(cat, r)
    _check_restaurants(cat, r)
    _check_restaurant_availability(cat, r)
    _check_hospitals(cat, r)
    _check_doctors(cat, r)
    _check_doctor_availability(cat, r)
    _check_speciality_mapping(cat, r)
    _check_test_calls(cat, r)
    _check_agent_phrases(cat, r)
    return r


# ---------------------------------------------------------------------------


def _check_sample_flags(cat: Catalog, r: Report) -> None:
    groups = {
        "areas": [(a.area_id, a.is_sample_data) for a in cat.areas],
        "restaurants": [(x.restaurant_id, x.is_sample_data) for x in cat.restaurants],
        "hospitals": [(x.hospital_id, x.is_sample_data) for x in cat.hospitals],
        "doctors": [(x.doctor_id, x.is_sample_data) for x in cat.doctors],
    }
    for file, rows in groups.items():
        for ident, flag in rows:
            if flag is not True:
                r.error(f"{file}.json [{ident}]: is_sample_data must be true")


def _check_areas(cat: Catalog, r: Report) -> None:
    ids = [a.area_id for a in cat.areas]
    if len(ids) != 2:
        r.error(f"areas.json: expected exactly 2 areas, found {len(ids)}")
    for d in _dupes(ids):
        r.error(f"areas.json: duplicate area_id {d}")
    for a in cat.areas:
        if len(a.aliases) < 3:
            r.warn(f"areas.json [{a.area_id}]: only {len(a.aliases)} aliases (aim for 6-10)")
        if any(al != al.lower() for al in a.aliases):
            r.warn(f"areas.json [{a.area_id}]: aliases should be lower-case")
        if not a.nearby_unsupported_areas:
            r.warn(f"areas.json [{a.area_id}]: no nearby_unsupported_areas")


def _check_restaurants(cat: Catalog, r: Report) -> None:
    area_ids = {a.area_id for a in cat.areas}
    for d in _dupes([x.restaurant_id for x in cat.restaurants]):
        r.error(f"restaurants.json: duplicate restaurant_id {d}")
    for d in _dupes([x.slug for x in cat.restaurants]):
        r.error(f"restaurants.json: duplicate slug {d}")

    per_area = Counter(x.area_id for x in cat.restaurants)
    for area in area_ids:
        if per_area[area] != PER_AREA:
            r.error(f"restaurants.json: area {area} has {per_area[area]} restaurants, need exactly {PER_AREA}")

    for x in cat.restaurants:
        tag = f"restaurants.json [{x.restaurant_id}]"
        if x.area_id not in area_ids:
            r.error(f"{tag}: unknown area_id {x.area_id}")
        missing_days = [d for d in DAYS if d not in x.opening_hours]
        if missing_days:
            r.error(f"{tag}: opening_hours missing {', '.join(missing_days)}")
        for d in DAYS:
            if d in x.opening_hours and not restaurant_times(x, d):
                r.error(f"{tag}: no bookable time on {d} (must be open every day; see CONTRACTS §7 weekday rule)")
        for d in _dupes([t.table_id for t in x.tables]):
            r.error(f"{tag}: duplicate table_id {d}")
        rules = x.booking_rules
        if rules.deposit_required_for_party_size_at_least > rules.max_party_size:
            r.error(f"{tag}: deposit threshold above max_party_size")
        largest = max(t.capacity for t in x.tables)
        if rules.max_party_size > largest:
            # One party = one table in this demo, so a bigger party could never be seated.
            r.error(f"{tag}: max_party_size {rules.max_party_size} is bigger than the largest table ({largest})")
        if not 8 <= len(x.tables) <= 12:
            r.warn(f"{tag}: {len(x.tables)} tables (aim for 8-12)")
        if not 3.8 <= x.rating <= 4.8:
            r.warn(f"{tag}: rating {x.rating} outside 3.8-4.8")
        if not 4 <= len(x.faqs) <= 5:
            r.warn(f"{tag}: {len(x.faqs)} FAQs (aim for 4-5)")

    for area in area_ids:
        ratings = [x.rating for x in cat.restaurants if x.area_id == area]
        if len(set(ratings)) != len(ratings):
            r.warn(f"restaurants.json: repeated ratings in {area} (top-3 order becomes ambiguous)")


def _check_restaurant_availability(cat: Catalog, r: Report) -> None:
    rest = {x.restaurant_id: x for x in cat.restaurants}
    seen: Counter[tuple[str, int, str]] = Counter()
    full_slots: Counter[str] = Counter()
    blocked = 0
    for row in cat.restaurant_availability:
        tag = f"restaurant_availability.json [{row.restaurant_id} +{row.day_offset} {row.time}]"
        seen[(row.restaurant_id, row.day_offset, row.time)] += 1
        x = rest.get(row.restaurant_id)
        if x is None:
            r.error(f"{tag}: unknown restaurant_id")
            continue
        if row.time not in BOOKABLE_TIMES:
            r.error(f"{tag}: {row.time} is not a bookable start time ({', '.join(BOOKABLE_TIMES)})")
        elif any(row.time not in restaurant_times(x, d) for d in DAYS):
            r.error(f"{tag}: {row.time} is outside opening hours on some weekday")
        table_ids = {t.table_id for t in x.tables}
        for t in row.booked_table_ids:
            if t not in table_ids:
                r.error(f"{tag}: booked table {t} does not exist in {x.restaurant_id}")
        for d in _dupes(row.booked_table_ids):
            r.error(f"{tag}: table {d} listed twice")
        if row.blocked:
            blocked += 1
            if row.booked_table_ids:
                r.warn(f"{tag}: blocked slot also lists booked tables")
        if set(row.booked_table_ids) >= table_ids:
            full_slots[row.restaurant_id] += 1
    for key, n in seen.items():
        if n > 1:
            r.error(f"restaurant_availability.json: duplicate row for {key}")
    for rid in rest:
        if full_slots[rid] < 2:
            r.warn(f"restaurant_availability.json: {rid} has {full_slots[rid]} fully booked slots (aim for >= 2)")
    if blocked == 0:
        r.warn("restaurant_availability.json: no blocked slots (aim for 2-3)")


def _check_hospitals(cat: Catalog, r: Report) -> None:
    area_ids = {a.area_id for a in cat.areas}
    for d in _dupes([x.hospital_id for x in cat.hospitals]):
        r.error(f"hospitals.json: duplicate hospital_id {d}")
    for d in _dupes([x.slug for x in cat.hospitals]):
        r.error(f"hospitals.json: duplicate slug {d}")
    per_area = Counter(x.area_id for x in cat.hospitals)
    for area in area_ids:
        if per_area[area] != PER_AREA:
            r.error(f"hospitals.json: area {area} has {per_area[area]} hospitals, need exactly {PER_AREA}")
        covered = {s for x in cat.hospitals if x.area_id == area for s in x.specialities}
        for s in SPECIALITIES:
            if s not in covered:
                r.error(f"hospitals.json: no hospital in {area} offers {s}")
    for x in cat.hospitals:
        tag = f"hospitals.json [{x.hospital_id}]"
        if x.area_id not in area_ids:
            r.error(f"{tag}: unknown area_id {x.area_id}")
        for d in _dupes(list(x.specialities)):
            r.error(f"{tag}: speciality {d} listed twice")
        for d in DAYS:
            value = x.opd_hours.get(d)  # type: ignore[call-overload]
            if value is None:
                r.error(f"{tag}: opd_hours missing {d}")
            elif value:
                try:
                    parse_range(value)
                except ValueError:
                    r.error(f"{tag}: opd_hours.{d} {value!r} is not 'HH:MM-HH:MM'")
        if not 4 <= len(x.faqs) <= 5:
            r.warn(f"{tag}: {len(x.faqs)} FAQs (aim for 4-5)")


def _check_doctors(cat: Catalog, r: Report) -> None:
    hosp = {x.hospital_id: x for x in cat.hospitals}
    for d in _dupes([x.doctor_id for x in cat.doctors]):
        r.error(f"doctors.json: duplicate doctor_id {d}")
    for doc in cat.doctors:
        tag = f"doctors.json [{doc.doctor_id}]"
        h = hosp.get(doc.hospital_id)
        if h is None:
            r.error(f"{tag}: unknown hospital_id {doc.hospital_id}")
            continue
        if doc.speciality not in h.specialities:
            r.error(f"{tag}: {doc.speciality} is not offered by {h.hospital_id}")
        if not doc.schedule:
            r.error(f"{tag}: empty schedule")
        for day, rng in doc.schedule.items():
            lo, hi = parse_range(rng)
            if lo % doc.slot_length_minutes or hi % doc.slot_length_minutes:
                r.error(f"{tag}: schedule.{day} {rng} is not on the {doc.slot_length_minutes}-minute grid")
            opd = opd_range(h, day)
            if opd is None or lo < opd[0] or hi > opd[1]:
                r.error(f"{tag}: schedule.{day} {rng} is outside {h.hospital_id} OPD hours")
    # Every speciality offered somewhere needs a doctor there.
    for h in cat.hospitals:
        offered = {doc.speciality for doc in cat.doctors if doc.hospital_id == h.hospital_id}
        for s in h.specialities:
            if s not in offered:
                r.error(f"hospitals.json [{h.hospital_id}]: offers {s} but has no doctor for it")
    on_leave = [doc for doc in cat.doctors if doc.on_leave_day_offsets]
    if not on_leave:
        r.warn("doctors.json: no doctor on leave (aim for exactly one)")
    for doc in on_leave:
        _require_daily(doc, "has on_leave_day_offsets", r)


def _require_daily(doc: Doctor, why: str, r: Report) -> None:
    if not works_every_day(doc):
        r.error(
            f"doctors.json [{doc.doctor_id}]: {why}, so it must work all 7 days "
            "(CONTRACTS §7 weekday rule)"
        )


def _check_doctor_availability(cat: Catalog, r: Report) -> None:
    docs = {d.doctor_id: d for d in cat.doctors}
    seen: Counter[tuple[str, int]] = Counter()
    fully_booked_tomorrow = False
    blocked = 0
    flagged: set[str] = set()
    for row in cat.doctor_availability:
        tag = f"doctor_availability.json [{row.doctor_id} +{row.day_offset}]"
        seen[(row.doctor_id, row.day_offset)] += 1
        doc = docs.get(row.doctor_id)
        if doc is None:
            r.error(f"{tag}: unknown doctor_id")
            continue
        if doc.doctor_id not in flagged:
            flagged.add(doc.doctor_id)
            _require_daily(doc, "appears in doctor_availability.json", r)
        valid = set(every_day_times(doc))
        for t in row.booked_times + row.blocked_times:
            if valid and t not in valid:
                r.error(f"{tag}: {t} is not a slot on every weekday of the schedule")
        for d in _dupes(row.booked_times + row.blocked_times):
            r.error(f"{tag}: time {d} listed twice (booked and/or blocked)")
        blocked += len(row.blocked_times)
        if row.day_offset == 1 and valid and set(row.booked_times) >= valid:
            fully_booked_tomorrow = True
    for key, n in seen.items():
        if n > 1:
            r.error(f"doctor_availability.json: duplicate row for {key}")
    if not fully_booked_tomorrow:
        r.warn("doctor_availability.json: no doctor fully booked tomorrow (aim for >= 1)")
    if blocked == 0:
        r.warn("doctor_availability.json: no blocked times (aim for 1-2)")


def _check_speciality_mapping(cat: Catalog, r: Report) -> None:
    m = cat.speciality_mapping
    if len(m.phrases) < MIN_PHRASES:
        r.error(f"speciality_mapping.json: {len(m.phrases)} phrases, need >= {MIN_PHRASES}")
    if len(m.emergency_phrases) < MIN_EMERGENCY:
        r.error(f"speciality_mapping.json: {len(m.emergency_phrases)} emergency phrases, need >= {MIN_EMERGENCY}")
    covered = {p.speciality for p in m.phrases}
    for s in SPECIALITIES:
        if s not in covered:
            r.error(f"speciality_mapping.json: no phrase maps to {s}")
    for lang in ("te", "hi", "en"):
        if not any(p.lang == lang for p in m.phrases):
            r.error(f"speciality_mapping.json: no {lang} phrases")
        if not any(p.lang == lang for p in m.emergency_phrases):
            r.error(f"speciality_mapping.json: no {lang} emergency phrases")
    normal = {p.phrase.lower() for p in m.phrases}
    for e in m.emergency_phrases:
        if e.phrase.lower() in normal:
            r.error(f"speciality_mapping.json: {e.phrase!r} is both an emergency and a normal phrase")
    for lang, text in m.emergency_reply.model_dump().items():
        if "108" not in text or "112" not in text:
            r.error(f"speciality_mapping.json: emergency_reply.{lang} must mention 108 and 112")
    _check_self_harm(m, normal, r)


def _check_self_harm(m: SpecialityMapping, normal: set[str], r: Report) -> None:
    """Self-harm phrases get their own gentle reply: Tele-MANAS 14416 (+ 1-800-891-4416) and 112."""
    if not m.self_harm_phrases and m.self_harm_reply is None:
        r.warn("speciality_mapping.json: no self_harm_phrases / self_harm_reply (they share the 108/112 reply)")
        return
    if m.self_harm_reply is None:
        r.error("speciality_mapping.json: self_harm_phrases need a self_harm_reply")
        return
    for lang, text in m.self_harm_reply.model_dump().items():
        if "14416" not in text or "112" not in text:
            r.error(f"speciality_mapping.json: self_harm_reply.{lang} must mention Tele-MANAS 14416 and 112")
    emergency = {e.phrase.lower() for e in m.emergency_phrases}
    for lang in ("te", "hi", "en"):
        if not any(p.lang == lang for p in m.self_harm_phrases):
            r.warn(f"speciality_mapping.json: no {lang} self_harm_phrases")
    for p in m.self_harm_phrases:
        if p.phrase.lower() in normal or p.phrase.lower() in emergency:
            r.error(f"speciality_mapping.json: {p.phrase!r} is a self-harm phrase and also another kind")


def _check_test_calls(cat: Catalog, r: Report) -> None:
    tc = cat.test_calls
    if len(tc) != TEST_CALLS:
        r.error(f"test_calls.json: {len(tc)} calls, need exactly {TEST_CALLS}")
    for d in _dupes([t.test_id for t in tc]):
        r.error(f"test_calls.json: duplicate test_id {d}")
    by_service = Counter(t.service for t in tc)
    if by_service["restaurant"] != 20 or by_service["hospital"] != 20:
        r.error(f"test_calls.json: need 20 restaurant + 20 hospital, found {dict(by_service)}")
    by_lang: Counter[str] = Counter(t.language_mix for t in tc)
    for lang, (lo, hi) in LANG_SPLIT.items():
        if not lo <= by_lang[lang] <= hi:
            r.warn(f"test_calls.json: {by_lang[lang]} {lang} calls (aim for {lo}-{hi})")
    by_scenario: Counter[str] = Counter(t.scenario for t in tc)
    for s in SCENARIOS:
        if by_scenario[s] < 2:
            r.warn(f"test_calls.json: scenario {s} appears {by_scenario[s]} times (aim for >= 2)")

    areas = {a.area_id for a in cat.areas}
    rest = {x.restaurant_id: x for x in cat.restaurants}
    hosp = {x.hospital_id: x for x in cat.hospitals}
    docs = {d.doctor_id: d for d in cat.doctors}
    flagged: set[str] = set()
    for t in tc:
        tag = f"test_calls.json [{t.test_id}]"
        e = t.expected
        if e.area_id is not None and e.area_id not in areas:
            r.error(f"{tag}: unknown area_id {e.area_id}")
        if e.business_id is not None:
            biz = rest.get(e.business_id) if t.service == "restaurant" else hosp.get(e.business_id)
            if biz is None:
                r.error(f"{tag}: business_id {e.business_id} is not a {t.service}")
            elif e.area_id is not None and biz.area_id != e.area_id:
                r.error(f"{tag}: {e.business_id} is not in {e.area_id}")
        if e.doctor_id is not None:
            doc = docs.get(e.doctor_id)
            if doc is None:
                r.error(f"{tag}: unknown doctor_id {e.doctor_id}")
            else:
                if e.business_id is not None and doc.hospital_id != e.business_id:
                    r.error(f"{tag}: {e.doctor_id} does not work at {e.business_id}")
                if e.speciality is not None and doc.speciality != e.speciality:
                    r.error(f"{tag}: {e.doctor_id} is {doc.speciality}, expected {e.speciality}")
                if doc.doctor_id not in flagged:
                    flagged.add(doc.doctor_id)
                    _require_daily(doc, "is used in test_calls.json", r)
                common = every_day_times(doc)
                if e.time is not None and common and e.time not in common:
                    r.error(f"{tag}: {e.time} is not a slot of {e.doctor_id} on every weekday")
        if t.service == "restaurant" and e.business_id in rest and e.time is not None:
            x = rest[e.business_id]
            if any(e.time not in restaurant_times(x, d) for d in DAYS):
                r.error(f"{tag}: {e.time} is not bookable every day at {x.restaurant_id}")
        if e.outcome == "booked":
            needed = ["area_id", "business_id", "day_offset", "time"]
            needed += ["party_size"] if t.service == "restaurant" else ["doctor_id", "speciality"]
            for f in needed:
                if getattr(e, f) is None:
                    r.error(f"{tag}: outcome 'booked' needs expected.{f}")
        if t.scenario == "emergency" and e.outcome != "redirected_emergency":
            r.error(f"{tag}: emergency scenario must expect outcome redirected_emergency")
        if t.scenario == "unsupported_area" and e.outcome == "booked" and e.area_id is None:
            r.error(f"{tag}: unsupported_area that ends booked needs the supported area_id")


def _check_agent_phrases(cat: Catalog, r: Report) -> None:
    keys = [p.key for p in cat.agent_phrases]
    for d in _dupes(keys):
        r.error(f"agent_phrases.json: duplicate key {d}")
    for k in PHRASE_KEYS:
        if k not in keys:
            r.error(f"agent_phrases.json: missing key {k}")
    for k in keys:
        if k not in PHRASE_KEYS:
            r.warn(f"agent_phrases.json: extra key {k}")
    for p in cat.agent_phrases:
        for lang, lines in (("te-en", p.te_en), ("hi-en", p.hi_en), ("en-IN", p.en_in)):
            if len(lines) != 3:
                r.error(f"agent_phrases.json [{p.key}]: {lang} has {len(lines)} variations, need 3")
            if p.key == "greeting_with_ai_disclosure":
                for line in lines:
                    if not any(n in line for n in VAANI_SPELLINGS) or "AI" not in line:
                        r.error(f"agent_phrases.json [{p.key}]: {lang} line must say Vaani is an AI: {line!r}")
            if p.key == "emergency_redirect":
                for line in lines:
                    if "108" not in line or "112" not in line:
                        r.error(f"agent_phrases.json [{p.key}]: {lang} line must mention 108 and 112")
