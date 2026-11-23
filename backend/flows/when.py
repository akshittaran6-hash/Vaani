"""Dates and times from code-mixed Telugu / Hindi / Indian-English words.

The LLM passes the caller's own words ("kal raat saadhe aath", "repu enimidinnara",
"day after tomorrow 7:30 pm") and code turns them into ISO values, so calendar maths
never depends on the model. Ambiguous hours use the service's opening pattern.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Literal

from backend.text import norm

Kind = Literal["restaurant", "hospital"]

NUM = {
    # English
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    # Hindi
    "ek": 1,
    "do": 2,
    "teen": 3,
    "char": 4,
    "chaar": 4,
    "paanch": 5,
    "panch": 5,
    "chhe": 6,
    "che": 6,
    "chhah": 6,  # Sarvam STT (translit) spells six this way
    "chah": 6,
    "chhai": 6,
    "saat": 7,
    "aath": 8,
    "nau": 9,
    "das": 10,
    "gyarah": 11,
    "gyaarah": 11,
    "barah": 12,
    "baarah": 12,
    # Telugu
    "okati": 1,
    "oka": 1,
    "okka": 1,
    "rendu": 2,
    "moodu": 3,
    "mudu": 3,
    "naalugu": 4,
    "nalugu": 4,
    "aidu": 5,
    "aaru": 6,
    "edu": 7,
    "enimidi": 8,
    "tommidi": 9,
    "padi": 10,
    "padakondu": 11,
    "pannendu": 12,
}
# Telugu "<n>nnara" = n:30 (enimidinnara = 8:30) and "<n>gantalaki" = n:00
TE_HALF = {
    "okatinnara": 1,
    "rendunnara": 2,
    "moodunnara": 3,
    "mudunnara": 3,
    "naalugunnara": 4,
    "nalugunnara": 4,
    "aidunnara": 5,
    "aarunnara": 6,
    "edunnara": 7,
    "enimidinnara": 8,
    "tommidinnara": 9,
    "padinnara": 10,
    "padakondunnara": 11,
    "pannendunnara": 12,
}

TODAY = {"today", "aaj", "ivala", "ivvala", "eeroju", "tonight"}
TOMORROW = {"tomorrow", "kal", "repu", "tmrw", "tomoro"}
DAY_AFTER = {"parso", "parson", "parsoon", "parsun", "ellundi"}
WEEKDAYS = {
    0: {"monday", "mon", "somvar", "somvaar", "somavaram"},
    1: {"tuesday", "tue", "mangalvar", "mangalvaar", "mangalavaram"},
    2: {"wednesday", "wed", "budhvar", "budhvaar", "budhavaram"},
    3: {"thursday", "thu", "guruvar", "guruvaar", "veervaar", "guruvaram"},
    4: {"friday", "fri", "shukravar", "shukravaar", "shukravaram", "sukravaram"},
    5: {"saturday", "sat", "shanivar", "shanivaar", "shanivaram"},
    6: {"sunday", "sun", "ravivar", "ravivaar", "itvaar", "aadivaram", "adivaram"},
}

PM_CUES = {
    "pm",
    "p.m",
    "raat",
    "raatri",
    "rathri",
    "ratri",
    "night",
    "shaam",
    "sham",
    "evening",
    "saayantram",
    "sayantram",
    "dinner",
}
AM_CUES = {"am", "a.m", "subah", "morning", "podduna", "poddunne", "udayam", "breakfast"}
NOON_CUES = {"noon", "dopahar", "afternoon", "madhyahnam", "lunch"}


def parse_day(text: str, today: date) -> date | None:
    t = norm(text)
    iso = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", text)
    if iso:
        return date(int(iso[1]), int(iso[2]), int(iso[3]))
    words = t.split()
    if "day after tomorrow" in t or any(w in DAY_AFTER for w in words):
        return today + timedelta(days=2)
    # "3 din baad", "naalugu rojula tarvata", "in 3 days", "3 days from now", "after 4 days"
    m = re.search(r"\b(\w+) (?:din|dino|days?|rojula|rojulu|roju)\b", t)
    if m and (n := _num(m[1])) is not None and re.search(r"baad|tarvata|taravata|from now|later|after|\bin\b", t):
        return today + timedelta(days=n)
    if any(w in TOMORROW for w in words):
        return today + timedelta(days=1)
    if any(w in TODAY for w in words) or "ee roju" in t or "this evening" in t:
        return today
    for wd, names in WEEKDAYS.items():
        if any(w in names for w in words):
            return today + timedelta(days=(wd - today.weekday()) % 7)
    return None


def _num(word: str) -> int | None:
    if word.isdigit():
        return int(word)
    return NUM.get(word)


def parse_time(text: str, kind: Kind = "restaurant") -> str | None:
    # Clock times are matched on the raw text: norm() turns ":" into a space. "8.30" = "8:30".
    raw = re.sub(r"(\d)\.(\d\d)\b", r"\1:\2", text.lower())
    t = norm(raw)
    words = set(t.split())
    if "noon" in words and (not re.search(r"\d", t) or re.search(r"\b12\s*noon\b", t)):
        return "12:00"

    hour: int | None = None
    minute = 0
    if m := re.search(r"\b(\d{1,2}):(\d{2})\b", raw):
        hour, minute = int(m[1]), int(m[2])
    elif m := re.search(r"\b(\d{1,2})\s*(am|pm)\b", t):
        hour = int(m[1])
    elif m := re.search(r"\b(saadhe|sadhe|sava|paune)\s+(\w+)", t):
        n = _num(m[2])
        if n is not None:
            hour, minute = {"saadhe": (n, 30), "sadhe": (n, 30), "sava": (n, 15), "paune": (n - 1 or 12, 45)}[m[1]]
    elif any(w in TE_HALF for w in words):
        hour, minute = next(TE_HALF[w] for w in t.split() if w in TE_HALF), 30
    elif "dedh" in words:
        hour, minute = 1, 30
    elif "dhai" in words:
        hour, minute = 2, 30
    elif hits := [
        _num(m[1]) for m in re.finditer(r"\b(\d{1,2}|\w+)\s*(?:baje|bajey|o'?clock|gantalaki|gantaki|ganta|ki)\b", t)
    ]:
        # "lunch ki aaruguru, okati gantaki" → the last <number> ki/baje wins (skip "lunch ki")
        hour = next((h for h in reversed(hits) if h is not None), None)
    elif m := re.search(r"\bat (\d{1,2})\b", t):
        hour = int(m[1])

    if hour is None or not (0 <= hour <= 24) or not (0 <= minute < 60):
        return None
    cues = words | set(re.findall(r"\d\s*(am|pm)", t))
    # Prefer a part-of-day word right next to the number: in "Udayam clinic, shaam 6 baje" the
    # clinic's name ("udayam" = morning in Telugu) must not beat "shaam" (evening).
    tokens = t.split()
    num_idx = [i for i, w in enumerate(tokens) if re.search(r"\d", w) or w in NUM or w in TE_HALF]
    if num_idx:
        i = num_idx[-1]
        near = set(tokens[max(0, i - 2) : i + 3]) | set(re.findall(r"\d\s*(am|pm)", t))
        if near & (AM_CUES | PM_CUES | NOON_CUES):
            cues = near
    hour = _resolve_period(hour, cues, kind)
    return f"{hour:02d}:{minute:02d}"


def _resolve_period(hour: int, words: set[str], kind: Kind) -> int:
    if hour >= 13 or hour == 0:
        return hour
    if words & AM_CUES:
        return 0 if hour == 12 else hour
    if words & PM_CUES:
        return hour if hour == 12 else hour + 12
    if words & NOON_CUES:
        return hour if hour >= 11 else hour + 12
    if hour == 12:
        return 12
    # No cue: restaurants serve lunch 12:30-14:00 and dinner 19:00-21:30 → 1-11 are afternoon/evening.
    if kind == "restaurant":
        return hour + 12
    # Doctors work ~09:00-20:00 → 8-11 morning, 1-7 afternoon/evening.
    return hour if hour >= 8 else hour + 12


_CORRECTION = re.compile(r"\b(ledu|kaadu|vaddu|nahi|nahin|no|not|actually|instead|balki|marchandi|change)\b", re.I)


def latest_time(text: str, kind: Kind = "restaurant") -> str | None:
    """The time the caller settled on: "4:30. Ledu, 5:30 ki marchandi" → 17:30 (last segment wins)."""
    for seg in reversed(_CORRECTION.split(text)):
        if seg and not _CORRECTION.fullmatch(seg) and (t := parse_time(seg, kind)):
            return t
    return None


def latest_day(text: str, today: date) -> date | None:
    for seg in reversed(_CORRECTION.split(text)):
        if seg and not _CORRECTION.fullmatch(seg) and (d := parse_day(seg, today)):
            return d
    return None
