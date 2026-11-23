"""Deterministic extraction from the caller's words: party size, the caller's name, and a
business or doctor they named. The eval showed the small fast LLM misreads these
("naluguru" → 1, "Coastal Kitchen" → a search in Gachibowli), so code reads them and
the LLM gets them as known facts.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from backend.catalog.models import Catalog, Doctor, Hospital, Restaurant
from backend.flows.when import NUM
from backend.text import norm

# Telugu people-counting words ("naluguru" = 4 people) and Hindi/English number words.
TE_PEOPLE = {
    "okkaru": 1,
    "iddaru": 2,
    "mugguru": 3,
    "naluguru": 4,
    "naaluguru": 4,
    "aiduguru": 5,
    "ayiduguru": 5,
    "aaruguru": 6,
    "eduguru": 7,
    "enimidimandi": 8,
    "tommidimandi": 9,
    "padimandi": 10,
}
# Telugu counting stems + endings: naluguru (4 people), naluguriki (for 4), naluguram (we 4),
# iddariki (for 2), mugguram (we 3), aaruguriki (for 6).
TE_PEOPLE_STEMS = {
    "okka": 1,
    "idda": 2,
    "muggu": 3,
    "nalugu": 4,
    "naalugu": 4,
    "aidugu": 5,
    "ayidugu": 5,
    "aarugu": 6,
    "edugu": 7,
}
_STEMS = "|".join(sorted(TE_PEOPLE_STEMS, key=len, reverse=True))
_TE_PEOPLE_RE = re.compile(rf"\b({_STEMS})(?:ru|riki|ram|rini|rum|ruki)\b")
PEOPLE_NOUNS = r"(?:people|persons|person|log|logon|logo|logg|mandi|members|guests|pax|adults)"
_CORRECTION = re.compile(r"\b(ledu|kaadu|vaddu|nahi|nahin|no|actually|instead|balki)\b")

NOT_NAMES = {
    "haan",
    "han",
    "avunu",
    "sare",
    "ok",
    "okay",
    "yes",
    "no",
    "ledu",
    "nahi",
    "theek",
    "thanks",
    "thank",
    "andi",
    "ji",
    "confirm",
    "please",
    "sure",
    "the",
    "a",
    "an",
    "table",
    "doctor",
    "dr",
    "book",
    "kal",
    "repu",
    "it",
    "for",
    "me",
    "my",
    "is",
    "and",
    "meeda",
    "mida",
    "pettandi",
    "pettu",
    "rakh",
    "rakhiye",
    "dijiye",
    "do",
    "se",
    "pe",
    "par",
    "ke",
    "ka",
    "ki",
    "hai",
    "patient",
    "lo",
    "undi",
    "cheyandi",
    "cheyyandi",
    "put",
    "under",
}


def _segments(text: str) -> list[str]:
    """Clauses, last first: "4 log. Nahi, 5 log" → ["5 log", "4 log"]."""
    return [s for s in reversed(_CORRECTION.split(norm(text))) if s and not _CORRECTION.fullmatch(s)]


def parse_party(text: str) -> int | None:
    for seg in _segments(text):
        words = seg.split()
        for w in reversed(words):
            if w in TE_PEOPLE:
                return TE_PEOPLE[w]
        if hits := _TE_PEOPLE_RE.findall(seg):
            return TE_PEOPLE_STEMS[hits[-1]]
        joined = seg.replace(" mandi", "mandi")
        for w, count in TE_PEOPLE.items():
            if w.endswith("mandi") and w in joined:
                return count
        if m := re.search(r"\b(?:table for|for|party of)\s+(\d{1,2}|\w+)\b(?!\s*(?:pm|am|baje|:))", seg):
            n = _num(m[1])
            if n and 1 <= n <= 30 and not re.search(rf"{m[1]}\s*(?:pm|am|o'?clock|baje)", seg):
                return n
        if m := re.search(rf"\b(\d{{1,2}}|\w+)\s+{PEOPLE_NOUNS}\b", seg):
            n = _num(m[1])
            if n and 1 <= n <= 30:
                return n
        if m := re.search(r"\b(\d{1,2}|\w+) of us\b", seg):
            us = _num(m[1])
            if us:
                return us
        # "Change that to four, please" — a number *word* not followed by a time ("make it eight pm").
        if m := re.search(
            r"\b(?:change|make) (?:that|it) (?:to|for) ([a-z]+)\b(?!\s*(?:pm|am|baje|o'?clock|thirty|fifteen|:))",
            seg,
        ):
            n = NUM.get(m[1])
            if n and 1 <= n <= 30:
                return n
    return None


def _num(word: str) -> int | None:
    return int(word) if word.isdigit() else NUM.get(word)


_NAME_LEADS = (
    "my name is|name is|name's|naam hai|mera naam|naa peru|na peru|mee peru|peru|naam|name|"
    "i am|i'm|this is|it's for|its for|booking for"
)
_NAME_PATTERNS = [
    # Name before the marker: "Anuvi Selavolu peru meeda pettandi", "Reyan Dharavolu ke naam se".
    r"\b([a-z][a-z]+(?:\s+[a-z][a-z]+)?)\s+(?:peru meeda|peru mida|peru tho|ke naam se|ke naam pe|ke naam par)\b",
    r"\b(?:put it under|under the name|under)\s+([a-z][a-z]+(?:\s+[a-z][a-z]+)?)",
    rf"\b(?:{_NAME_LEADS})\s+([a-z][a-z]+(?:\s+[a-z][a-z]+)?)",
]


def parse_name(text: str, asked_for_name: bool = False) -> str | None:
    t = re.sub(r"[^\w\s']", " ", text.lower())
    for pat in _NAME_PATTERNS:
        if m := re.search(pat, t):
            words = [w for w in m[1].split() if w not in NOT_NAMES]
            # "Naam Pooja Verma." → "Pooja Verma"; stop at filler words ("peru Rajesh andi")
            if words:
                return " ".join(w.capitalize() for w in words[:2])
    if asked_for_name:
        words = re.findall(r"[a-z]+", t)
        if 1 <= len(words) <= 3 and not set(words) & NOT_NAMES:
            return " ".join(w.capitalize() for w in words)
    return None


def is_entity_name(name: str, catalog: Catalog) -> bool:
    """True if `name` is (part of) a doctor's or business's name: "Navisha Vaanavolu" is the
    doctor the caller asked for, not the patient (eval T29)."""
    key = norm(name)
    if len(key.split()) < 2:
        return False  # a lone first name ("Ravi") is a normal caller name even if a doctor shares it
    names: list[str] = [d.name.replace("Dr. ", "") for d in catalog.doctors]
    names += [r.name for r in catalog.restaurants] + [h.name for h in catalog.hospitals]
    return any(f" {key} " in f" {norm(n)} " for n in names)


def find_business(text: str, catalog: Catalog) -> Restaurant | Hospital | None:
    """The business named in the text (longest exact name/alias match)."""
    t = f" {norm(text)} "
    best: tuple[int, Restaurant | Hospital] | None = None
    businesses: list[Restaurant | Hospital] = [*catalog.restaurants, *catalog.hospitals]
    for b in businesses:
        for alias in [b.name, *b.name_aliases]:
            key = norm(alias)
            if len(key) >= 4 and f" {key} " in t and (best is None or len(key) > best[0]):
                best = (len(key), b)
    if best:
        return best[1]
    # STT spellings of multi-word names ("Vana Grove", "Dumgali Courtyard"): same-length word
    # windows, fuzzy ≥ 88, names of 8+ letters only (short ones like "Vaani" collide too easily).
    words = t.split()
    fuzzy: tuple[float, Restaurant | Hospital] | None = None
    for b in businesses:
        for alias in [b.name, *b.name_aliases]:
            key = norm(alias)
            n = len(key.split())
            if n < 2 or len(key) < 8:
                continue
            for i in range(len(words) - n + 1):
                score = fuzz.ratio(" ".join(words[i : i + n]), key)
                if score >= 88 and (fuzzy is None or score > fuzzy[0]):
                    fuzzy = (score, b)
    return fuzzy[1] if fuzzy else None


def find_doctor_named(
    text: str,
    catalog: Catalog,
    hospital_id: str | None = None,
    area_id: str | None = None,
    speciality: str | None = None,
) -> Doctor | None:
    """'Dr. Suvin Rellimudi garu', 'Dr. Suvin Relimudi' (STT spelling) → that doctor.

    First names repeat across hospitals (two Dr. Suvins, three Mihiras), so: the first name must
    match, a surname close to the doctor's (fuzzy ≥ 80) wins, then the call's hospital / area /
    speciality break ties. Still tied → None, so the agent asks instead of guessing (voice run:
    "Suvin Relimudi" once booked Dr. Suvin Harivelu at the other hospital)."""
    t = norm(text).replace("dr ", "dr. ")
    if "dr" not in t and "doctor" not in t:
        return None
    words = re.findall(r"[a-z]+", t)
    hospitals = {h.hospital_id: h for h in catalog.hospitals}
    scored: list[tuple[tuple[int, int, int, int], Doctor]] = []
    for d in catalog.doctors:
        first, *rest = norm(d.name.replace("Dr. ", "")).split()
        if not re.search(rf"\b{first}\b", t):
            continue
        last = rest[-1] if rest else ""
        surname = bool(last) and max((fuzz.ratio(w, last) for w in words if len(w) >= 4), default=0) >= 80
        titled = bool(re.search(rf"(dr\.?|doctor)\s+{first}\b", t))
        if not (surname or titled):
            continue
        h = hospitals.get(d.hospital_id)
        scored.append(
            (
                (
                    int(surname),
                    int(hospital_id == d.hospital_id),
                    int(bool(area_id) and h is not None and h.area_id == area_id),
                    int(speciality == d.speciality),
                ),
                d,
            )
        )
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None  # ambiguous ("Dr. Suvin" with no surname, area or hospital): ask, don't guess
    return scored[0][1]
