"""Text → what the TTS should say, in te / hi / en-IN.

Code-written lines and LLM replies contain digits ("raat 8:30", "₹650", "VN-4821", "6 log",
"Wed 25 Nov", "4.7"). TTS engines read those inconsistently, so we spell them out the way a
person in Hyderabad would say them:

    normalize("Kal raat 8:30, 6 log, ₹300 deposit", "hi")
      → "Kal raat saadhe aath baje, chhah log, teen sau rupaye deposit"
    normalize("repu raatri 8:30 ki", "te")  → "repu raatri enimidinnara ki"
    normalize("Tomorrow at 8:30 PM", "en")  → "Tomorrow at eight thirty PM"

Order matters: booking IDs and helpline numbers → ₹ amounts → times → dates → decimals →
remaining integers. Pure functions, no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Callable

Lang = str  # "te" | "hi" | "en"

# ---------------------------------------------------------------------------
# Number words
# ---------------------------------------------------------------------------

_EN_ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_EN_TENS = ["_", "_", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

# Hindi 0–99 are irregular, so a full table.
_HI = [
    "shunya",
    "ek",
    "do",
    "teen",
    "chaar",
    "paanch",
    "chhah",
    "saat",
    "aath",
    "nau",
    "das",
    "gyaarah",
    "baarah",
    "terah",
    "chaudah",
    "pandrah",
    "solah",
    "satrah",
    "athaarah",
    "unnees",
    "bees",
    "ikkees",
    "baaees",
    "teyees",
    "chaubees",
    "pachchees",
    "chhabbees",
    "sattaees",
    "atthaaees",
    "untees",
    "tees",
    "iktees",
    "battees",
    "taintees",
    "chauntees",
    "paintees",
    "chhattees",
    "saintees",
    "adtees",
    "untaalees",
    "chaalees",
    "iktaalees",
    "bayaalees",
    "taintaalees",
    "chavaalees",
    "paintaalees",
    "chhiyaalees",
    "saintaalees",
    "adtaalees",
    "unchaas",
    "pachaas",
    "ikyaavan",
    "baavan",
    "tirpan",
    "chauvan",
    "pachpan",
    "chhappan",
    "sattaavan",
    "atthaavan",
    "unsath",
    "saath",
    "iksath",
    "baasath",
    "tirsath",
    "chausath",
    "painsath",
    "chhiyaasath",
    "sadsath",
    "adsath",
    "unhattar",
    "sattar",
    "ikhattar",
    "bahattar",
    "tihattar",
    "chauhattar",
    "pachhattar",
    "chhihattar",
    "satattar",
    "athattar",
    "unaasi",
    "assi",
    "ikyaasi",
    "bayaasi",
    "tiraasi",
    "chauraasi",
    "pachaasi",
    "chhiyaasi",
    "sattaasi",
    "athaasi",
    "navaasi",
    "nabbe",
    "ikyaanve",
    "baanve",
    "tiraanve",
    "chauraanve",
    "pachaanve",
    "chhiyaanve",
    "sattaanve",
    "atthaanve",
    "ninyaanve",
]

_TE_ONES = [
    "sunna",
    "okati",
    "rendu",
    "moodu",
    "naalugu",
    "aidu",
    "aaru",
    "edu",
    "enimidi",
    "tommidi",
    "padi",
    "padakondu",
    "pannendu",
    "padamoodu",
    "padhnaalugu",
    "padihenu",
    "padahaaru",
    "padihedu",
    "paddenimidi",
    "pandommidi",
]
_TE_TENS = ["_", "_", "iravai", "muppai", "nalabhai", "yabhai", "aravai", "debbai", "enabhai", "tombhai"]
_TE_HUNDREDS = {1: "vanda", 2: "rendu vandalu", 3: "moodu vandalu", 4: "naalugu vandalu", 5: "aidu vandalu"}

assert len(_HI) == 100 and len(_EN_ONES) == 20 and len(_TE_ONES) == 20


def _en(n: int) -> str:
    if n < 20:
        return _EN_ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _EN_TENS[tens] + (f" {_EN_ONES[ones]}" if ones else "")
    if n < 1000:
        h, rest = divmod(n, 100)
        return f"{_EN_ONES[h]} hundred" + (f" {_en(rest)}" if rest else "")
    if n < 100_000:
        th, rest = divmod(n, 1000)
        return f"{_en(th)} thousand" + (f" {_en(rest)}" if rest else "")
    lakh, rest = divmod(n, 100_000)
    return f"{_en(lakh)} lakh" + (f" {_en(rest)}" if rest else "")


def _hi(n: int) -> str:
    if n < 100:
        return _HI[n]
    if n < 1000:
        h, rest = divmod(n, 100)
        return f"{_HI[h]} sau" + (f" {_HI[rest]}" if rest else "")
    if n < 100_000:
        th, rest = divmod(n, 1000)
        return f"{_hi(th)} hazaar" + (f" {_hi(rest)}" if rest else "")
    lakh, rest = divmod(n, 100_000)
    return f"{_hi(lakh)} laakh" + (f" {_hi(rest)}" if rest else "")


def _te(n: int) -> str:
    if n < 20:
        return _TE_ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TE_TENS[tens] + (f" {_TE_ONES[ones]}" if ones else "")
    if n < 1000:
        h, rest = divmod(n, 100)
        if not rest:
            return _TE_HUNDREDS.get(h, f"{_TE_ONES[h]} vandalu")
        # "aaru vandala yabhai" (650): the combining form ends in -la
        head = "nuta" if h == 1 else f"{_TE_ONES[h]} vandala"
        return f"{head} {_te(rest)}"
    if n < 100_000:
        th, rest = divmod(n, 1000)
        if not rest:
            return "veyyi" if th == 1 else f"{_te(th)} velu"
        return ("veyyi" if th == 1 else f"{_te(th)} vela") + f" {_te(rest)}"
    lakh, rest = divmod(n, 100_000)
    return f"{_te(lakh)} lakshalu" + (f" {_te(rest)}" if rest else "")


NUMBER: dict[str, Callable[[int], str]] = {"en": _en, "hi": _hi, "te": _te}


def number_words(n: int, lang: Lang) -> str:
    return NUMBER.get(lang, _en)(n)


def digits_words(digits: str, lang: Lang) -> str:
    """'4821' → 'four eight two one' / 'chaar aath do ek' / 'naalugu enimidi rendu okati'."""
    return " ".join(number_words(int(d), lang) for d in digits if d.isdigit())


# ---------------------------------------------------------------------------
# Times
# ---------------------------------------------------------------------------

_TE_HALF = {
    1: "okatinnara",
    2: "rendunnara",
    3: "moodunnara",
    4: "naalugunnara",
    5: "aidunnara",
    6: "aarunnara",
    7: "edunnara",
    8: "enimidinnara",
    9: "tommidinnara",
    10: "padinnara",
    11: "padakondunnara",
    12: "pannendunnara",
}
PART_OF_DAY = {
    "te": [(12, "podduna"), (16, "madhyaanam"), (19, "saayantram"), (24, "raatri")],
    "hi": [(12, "subah"), (16, "dopahar"), (19, "shaam"), (24, "raat")],
}
_PART_WORDS = {w for parts in PART_OF_DAY.values() for _, w in parts} | {
    "raathri",
    "rathri",
    "sayantram",
    "madhyahnam",
    "sham",
    "subha",
}


def _clock12(h: int) -> int:
    return h % 12 or 12


def _hi_time(h: int, m: int) -> str:
    """Hindi clock phrase without a part-of-day word: saadhe aath baje, sava saat, paune nau."""
    h12 = _clock12(h)
    if m == 0:
        return f"{_HI[h12]} baje"
    if m == 30:
        if h12 == 1:
            return "dedh baje"
        if h12 == 2:
            return "dhaai baje"
        return f"saadhe {_HI[h12]} baje"
    if m == 15:
        return f"sava {_HI[h12]} baje"
    if m == 45:
        nxt = _clock12(h12 + 1)
        return f"paune {_HI[nxt]} baje"
    return f"{_HI[h12]} baj kar {_HI[m]} minute"


def _te_time(h: int, m: int) -> str:
    """Telugu: enimidi gantalaki (8:00), enimidinnara (8:30), enimidimpaavu (8:15), …"""
    h12 = _clock12(h)
    word = _TE_ONES[h12]
    if m == 0:
        return f"{word} gantalaki"
    if m == 30:
        return _TE_HALF[h12]
    if m == 15:
        return f"{word} paavu"
    if m == 45:
        return f"{word} mukkaalu"
    return f"{word} gantala {_te(m)} nimishalaki"


def _en_time(h: int, m: int, ampm: str | None) -> str:
    h12 = _clock12(h)
    suffix = ampm or ("AM" if h < 12 else "PM")
    if m == 0:
        return f"{_en(h12)} {suffix}"
    mins = f"oh {_en(m)}" if m < 10 else _en(m)
    return f"{_en(h12)} {mins} {suffix}"


def _part_of_day(h: int, lang: Lang) -> str:
    return next(word for limit, word in PART_OF_DAY.get(lang, PART_OF_DAY["hi"]) if h < limit)


# "raat 8:30", "8:30 PM", "20:30", "shaam 7" (a part-of-day word before a bare hour),
# optionally followed by "baje" / "ki" / "ko", which the spoken form absorbs.
_TIME = re.compile(
    r"(?P<part>\b(?:" + "|".join(sorted(_PART_WORDS, key=len, reverse=True)) + r")\s+)?"
    r"\b(?P<h>[01]?\d|2[0-3])(?::(?P<m>[0-5]\d)"
    # a bare hour only before a space/punctuation/am-pm, and never before a people word ("raat 6 log")
    r"|(?P<bare>(?=\s|,|\.|\?|!|$|[AaPp]\.?[Mm])(?!\s+(?:log|logon|logo|mandi|people|persons|guests|members)\b)))"
    r"(?:\s*(?P<ampm>[AaPp]\.?\s?[Mm]\.?)(?![a-z]))?"
    r"(?P<tail>\s+(?:baje|ki|ko)\b)?",
)


def _time_sub(lang: Lang) -> Callable[[re.Match[str]], str]:
    def sub(m: re.Match[str]) -> str:
        part, ampm, tail = m["part"], m["ampm"], m["tail"]
        hour, minute = int(m["h"]), int(m["m"] or 0)
        if m["bare"] is not None and not (part or ampm):
            return m[0]  # a plain number ("6 log"): not a time
        if hour > 23:
            return m[0]
        if ampm:
            pm = ampm.lower().startswith("p")
            hour = hour % 12 + (12 if pm else 0)
            ampm = "PM" if pm else "AM"
        elif part:
            p = part.strip().lower()
            evening = p in {"shaam", "sham", "raat", "raatri", "raathri", "rathri", "saayantram", "sayantram"}
            if evening and hour < 12 or p in {"dopahar", "madhyaanam", "madhyahnam"} and hour < 6:
                hour += 12
        if lang == "en":
            prefix = part or ""
            return f"{prefix}{_en_time(hour, minute, ampm)}"
        spoken = _hi_time(hour, minute) if lang == "hi" else _te_time(hour, minute)
        # Keep the caller-facing part-of-day word; add one for 24h input ("20:30").
        prefix = part if part else (f"{_part_of_day(hour, lang)} " if (m["m"] and not ampm and hour >= 12) else "")
        keep_tail = ""
        if tail:
            t = tail.strip().lower()
            # "8:30 ki" (te) keeps "ki"; "7 baje" (hi) is already in the spoken form.
            if lang == "te" and t == "ki" and not spoken.endswith("ki"):
                keep_tail = " ki"
            elif lang == "hi" and t in ("ko",):
                keep_tail = " ko"
        return f"{prefix}{spoken}{keep_tail}"

    return sub


# ---------------------------------------------------------------------------
# Other patterns
# ---------------------------------------------------------------------------

_BOOKING_ID = re.compile(r"\b([A-Z]{2})-(\d{3,6})\b")
_HELPLINE = re.compile(r"\b(1-800-\d{3}-\d{4}|108|112|14416)\b")
_MONEY = re.compile(
    r"(?:₹\s*|\b(?:rs\.?|inr)\s*)(\d[\d,]*)(?:\s*(?:rupaye|rupees|rupee|rupayalu)\b)?"
    r"|\b(\d[\d,]*)\s*(?:rupaye|rupay|rupees|rupee|rupayalu|रुपये|రూపాయలు)",
    re.IGNORECASE,
)
_RUPEES = {"en": "rupees", "hi": "rupaye", "te": "rupayalu"}
_LONG_DIGITS = re.compile(r"\b\d{5,}\b")
_DECIMAL = re.compile(r"\b(\d+)\.(\d+)\b")
_ORDINAL = re.compile(r"\b(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)
_INT = re.compile(r"\b\d{1,4}\b")
_WEEKDAYS = {
    "Mon": "Monday",
    "Tue": "Tuesday",
    "Wed": "Wednesday",
    "Thu": "Thursday",
    "Fri": "Friday",
    "Sat": "Saturday",
    "Sun": "Sunday",
}
_MONTHS = {
    "Jan": "January",
    "Feb": "February",
    "Mar": "March",
    "Apr": "April",
    "Jun": "June",
    "Jul": "July",
    "Aug": "August",
    "Sep": "September",
    "Oct": "October",
    "Nov": "November",
    "Dec": "December",
}
_DATE = re.compile(
    r"\b(?:(?P<wd>Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+)?(?P<d>\d{1,2})\s+(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b"
)
_EN_ORD = {1: "first", 2: "second", 3: "third", 5: "fifth", 8: "eighth", 9: "ninth", 12: "twelfth"}


def _en_ordinal(n: int) -> str:
    if n in _EN_ORD:
        return _EN_ORD[n]
    if n < 20:
        return _en(n) + "th"
    tens, ones = divmod(n, 10)
    if not ones:
        return _EN_TENS[tens][:-1] + "ieth"
    return f"{_EN_TENS[tens]} {_en_ordinal(ones)}"


def _date_sub(lang: Lang) -> Callable[[re.Match[str]], str]:
    def sub(m: re.Match[str]) -> str:
        day = int(m["d"])
        month = _MONTHS.get(m["mon"], m["mon"])
        wd = f"{_WEEKDAYS[m['wd']]} " if m["wd"] else ""
        if lang == "en":
            return f"{wd}{_en_ordinal(day)} {month}"
        return f"{wd}{number_words(day, lang)} {month}"

    return sub


def money_words(n: int, lang: Lang) -> str:
    """650 → 'six hundred fifty rupees' / 'chhah sau pachaas rupaye' / 'aaru vandala yabhai rupayalu'."""
    words = number_words(n, lang)
    if lang == "te":
        words = re.sub(r"vandalu$", "vandala", words)  # "aaru vandala rupayalu"
        words = re.sub(r"^vanda$", "vanda", words)
    return f"{words} {_RUPEES[lang]}"


def normalize(text: str, lang: Lang) -> str:
    """Spell out IDs, helplines, money, times, dates and numbers for TTS in `lang`."""
    if not text:
        return text
    lang = lang if lang in NUMBER else "en"
    # IDs and helplines are read digit by digit in English in every language ("V N four eight
    # two one", "one one two"): how people read them out, and the same inside Telugu/Devanagari script.
    out = _BOOKING_ID.sub(lambda m: f"{' '.join(m[1])} {digits_words(m[2], 'en')}", text)
    out = _HELPLINE.sub(lambda m: digits_words(m[1], "en"), out)
    out = _MONEY.sub(lambda m: money_words(int((m[1] or m[2]).replace(",", "")), lang), out)
    out = _LONG_DIGITS.sub(lambda m: digits_words(m[0], lang), out)
    out = _TIME.sub(_time_sub(lang), out)
    out = _DATE.sub(_date_sub(lang), out)
    out = _ORDINAL.sub(lambda m: _en_ordinal(int(m[1])) if lang == "en" else number_words(int(m[1]), lang), out)
    point = {"en": "point", "hi": "point", "te": "point"}[lang]
    out = _DECIMAL.sub(lambda m: f"{number_words(int(m[1]), lang)} {point} {digits_words(m[2], lang)}", out)
    out = _INT.sub(lambda m: number_words(int(m[0]), lang), out)
    return re.sub(r"\s{2,}", " ", out).strip()
