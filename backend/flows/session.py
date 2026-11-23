"""One call, in text: greet → (guards) → LLM action loop → reply. Same nodes, rules and
events the voice pipeline will use in Phase 4.

Per caller turn:
1. transcript + `transcript` event; on the first turn detect the language (`language_detected`).
2. Deterministic guards, before any LLM call: an emergency phrase in a router/hospital call
   gets the 108/112 line and no LLM; OTP / PIN / card numbers are redacted and refused.
3. LLM loop (≤ MAX_STEPS): system prompt rebuilt from the current node → JSON reply →
   run the actions → feed back <tool_results> → stop at a reply with no actions.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

from backend.api.deps import Services
from backend.clock import today_ist
from backend.flows import prompts
from backend.flows.context import CallContext
from backend.flows.extract import find_business, find_doctor_named, is_entity_name, parse_name, parse_party
from backend.flows.language import detect_language
from backend.flows.nodes import NODES, FunctionSpec, functions_for
from backend.flows.when import latest_day, latest_time
from backend.text import mask_phone, norm
from backend.tools.hospitals import find_emergency, find_speciality_phrase
from backend.voice.llm import LLM, LLMReply

log = logging.getLogger(__name__)

MAX_STEPS = 6
MAX_ACTIONS_PER_STEP = 3
HISTORY_TURNS = 24  # messages kept (plus the system prompt)
LANG_NAMES = {"te": "Telugu-English (te-en)", "hi": "Hindi-English (hi-en)", "en": "Indian English (en-IN)"}
PHRASE_LANG = {"te": "te_en", "hi": "hi_en", "en": "en_in"}
SECRET_WORDS = re.compile(
    r"\b(otp|o\.t\.p|cvv|pin|upi pin|card number|account number|debit card|credit card|password)\b", re.I
)
LONG_DIGITS = re.compile(r"\d(?:[\s-]?\d){5,}")  # 6+ digits, spaces/dashes allowed (OTPs, card numbers)
ANY_DIGITS = re.compile(r"\d(?:[\s-]?\d)*")
# Common Hyderabad localities outside the demo areas (plus each area's nearby list from data/).
OTHER_AREAS = {
    "secunderabad",
    "kukatpally",
    "kphb",
    "ameerpet",
    "hitech city",
    "hi-tech city",
    "madhapur",
    "kondapur",
    "banjara hills",
    "begumpet",
    "dilsukhnagar",
    "kompally",
    "miyapur",
    "lb nagar",
    "uppal",
    "mehdipatnam",
    "charminar",
    "tolichowki",
    "manikonda",
    "nanakramguda",
    "financial district",
    "somajiguda",
    "panjagutta",
    "abids",
    "koti",
    "malakpet",
    "attapur",
    "tarnaka",
    "habsiguda",
    "kothapet",
    "chandanagar",
    "lingampally",
    "nizampet",
    "bachupally",
    "shamshabad",
    "film nagar",
    "yousufguda",
    "himayatnagar",
    "narayanguda",
    "sr nagar",
    "erragadda",
    "bowenpally",
    "alwal",
    "ecil",
    "nampally",
    "masab tank",
    "jubilee bus stand",
}
RELATIVE_NEXT_DAY = re.compile(
    r"\b(day after that|the day after|next day|following day|agle din|uske agle din|marusati roju|marnadu)\b", re.I
)
FAQ_WORDS = {
    "parking",
    "insurance",
    "cashless",
    "wheelchair",
    "pharmacy",
    "ambulance",
    "24x7",
    "walk-in",
    "walkin",
    "lift",
    "lab",
    "timings",
    "timing",
    "opd",
    "vegetarian",
    "menu",
    "accessible",
}
KIDS_WORDS = {"kids", "kid", "children", "child", "bachchon", "bachon", "bachche", "pillalu", "pillalaki"}
BOOKING_WORDS = {"kavali", "chahiye", "need", "want", "book", "booking", "table", "appointment", "doctor", "slot"}
YES_WORDS = {
    "avunu",
    "avnu",
    "sare",
    "ok",
    "okay",
    "confirm",
    "cheyyandi",
    "cheyandi",
    "chey",
    "haan",
    "han",
    "ha",
    "haanji",
    "theek",
    "thik",
    "bilkul",
    "kardo",
    "kar",
    "do",
    "karo",
    "yes",
    "yeah",
    "yep",
    "sure",
    "please",
    "go",
    "ahead",
    "book",
    "it",
    "ji",
    "hai",
    "andi",
    "garu",
    "done",
    "perfect",
    "correct",
    "right",
    "chalega",
    "dijiye",
    "kijiye",
    "pettandi",
}
# A booking needs one of these in the caller's own turn (not just "nothing negative").
CORE_YES = {
    "avunu",
    "avnu",
    "sare",
    "ok",
    "okay",
    "confirm",
    "haan",
    "han",
    "ha",
    "haanji",
    "theek",
    "thik",
    "bilkul",
    "yes",
    "yeah",
    "yep",
    "sure",
    "correct",
    "chalega",
}
NO_WORDS = {
    "ledu",
    "kaadu",
    "vaddu",
    "nahi",
    "nahin",
    "no",
    "wait",
    "change",
    "instead",
    "actually",
    "but",
    "cancel",
    "aagu",
    "ruko",
}
# "₹650", "650 rupaye", "650 rupees", "650 రూపాయలు", "650 रुपये"
MONEY_RE = re.compile(
    r"₹\s*(\d[\d,]*)|(\d[\d,]*)\s*(?:rupaye|rupay|rupees|rupee|rupayalu|rs\b|inr\b|रुपये|रुपए|రూపాయలు)",
    re.IGNORECASE,
)
DAY_WORDS = {
    0: ("today", "aaj", "ivala"),
    1: ("tomorrow", "kal", "repu"),
    2: ("day after tomorrow", "parso", "parson", "ellundi"),
}


@dataclass
class TurnResult:
    reply: str
    fillers: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    guard: str | None = None


class Session:
    def __init__(self, svc: Services, llm: LLM, phone: str, channel: str = "web", language: str = "te") -> None:
        self.svc = svc
        self.catalog = svc.catalog
        self.settings = svc.settings
        self.llm = llm
        self.ctx = CallContext(phone=phone, channel=channel, language=language)  # type: ignore[arg-type]
        self.tools = svc.tool_context(phone=phone, language=language)
        self.history: list[dict[str, str]] = []

    # -- helpers used by node handlers -------------------------------------

    async def emit(self, type_: str, payload: dict[str, Any]) -> None:
        if self.ctx.call_id:
            await self.svc.store.emit(self.ctx.call_id, type_, payload)

    async def set_slot(self, key: str, value: Any) -> None:
        if self.ctx.slots.get(key) != value:
            self.ctx.slots[key] = value
            await self.emit("slot_filled", {"slot": key, "value": value})

    async def set_language(self, lang: str, via: str, confidence: float = 1.0) -> None:
        changed = lang != self.ctx.language
        self.ctx.language = lang
        self.tools.language = lang
        if changed or via != "agent":
            await self.emit("language_detected", {"lang": lang, "confidence": confidence, "via": via})

    def phrase(self, key: str, i: int | None = None) -> str:
        p = next((x for x in self.catalog.agent_phrases if x.key == key), None)
        if p is None:
            return ""
        lines: list[str] = getattr(p, PHRASE_LANG.get(self.ctx.language, "en_in"))
        idx = (self.ctx.turn if i is None else i) % len(lines)
        return lines[idx].replace("{area_1}", "Jubilee Hills").replace("{area_2}", "Gachibowli")

    def last_caller_text(self) -> str:
        return next((t["text"] for t in reversed(self.ctx.transcript) if t["speaker"] == "caller"), "")

    def day_words(self, d: date) -> str:
        delta = (d - today_ist()).days
        words = DAY_WORDS.get(delta)
        label = {"te": 2, "hi": 1, "en": 0}.get(self.ctx.language, 0)
        return f"{words[label]} ({d.strftime('%a %d %b')})" if words else d.strftime("%A %d %b")

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> str:
        self.ctx.call_id = await self.svc.store.start_call(self.ctx.channel, self.ctx.phone)
        self.tools.call_id = self.ctx.call_id
        await self.emit("call_started", {"channel": self.ctx.channel, "from_masked": mask_phone(self.ctx.phone)})
        greeting = self.phrase("greeting_with_ai_disclosure", 0)
        self.history.append(
            {"role": "assistant", "content": json.dumps({"say": greeting, "actions": []}, ensure_ascii=False)}
        )
        await self._log("vaani", greeting, self.ctx.language)
        return greeting

    async def handle(self, text: str) -> TurnResult:
        self.ctx.turn += 1
        # Guard 0 (privacy): redact OTPs / PINs / card numbers BEFORE anything is logged or sent.
        secret = bool(SECRET_WORDS.search(text) or LONG_DIGITS.search(text))
        if secret:
            text = (ANY_DIGITS if SECRET_WORDS.search(text) else LONG_DIGITS).sub("[redacted]", text)
        lang, conf = detect_language(text)
        if self.ctx.turn == 1:
            await self.set_language(lang, via="speech", confidence=conf)
        await self._log("caller", text, lang)
        kind: Literal["restaurant", "hospital"] = "hospital" if self.ctx.service == "hospital" else "restaurant"
        if t := latest_time(text, kind):
            self.ctx.heard_time = t
        if RELATIVE_NEXT_DAY.search(text) and self.ctx.heard_day and "day after tomorrow" not in text.lower():
            # "make it the day after that" / "the day after instead" = previously chosen day + 1
            self.ctx.heard_day = (date.fromisoformat(self.ctx.heard_day) + timedelta(days=1)).isoformat()
        elif d := latest_day(text, today_ist()):
            self.ctx.heard_day = d.isoformat()
        new_info = await self._extract(text)

        # Guard 1: emergency (router / hospital calls). No LLM, no booking.
        if self.ctx.service != "restaurant" and (hit := find_emergency(text, self.catalog)):
            self.ctx.emergency = True
            self.ctx.pending = None
            self.ctx.service = self.ctx.service or "hospital"
            reply = getattr(self.catalog.speciality_mapping.emergency_reply, self.ctx.language)
            await self.emit(
                "tool_called",
                {
                    "tool": "emergency_guard",
                    "summary": f"Emergency phrase “{hit}” → told caller to call 108 / 112",
                    "ms": 0,
                    "ok": True,
                },
            )
            return await self._finish_turn(text, TurnResult(reply=reply, guard="emergency"))

        # Guard 2: a locality outside the demo (and no demo area in the same sentence) → fixed polite reply.
        if (other := self._other_area(text)) and not self.ctx.slots.get("area_id"):
            self.ctx.unsupported_heard = other
            reply = self.catalog.areas[0].unsupported_area_reply.model_dump().get(self.ctx.language, "")
            await self.emit(
                "tool_called",
                {
                    "tool": "area_guard",
                    "summary": f"Area “{other}” not covered → offered Jubilee Hills / Gachibowli",
                    "ms": 0,
                    "ok": True,
                },
            )
            self.history.append({"role": "user", "content": text})
            self.history.append(
                {"role": "assistant", "content": json.dumps({"say": reply, "actions": []}, ensure_ascii=False)}
            )
            if self.ctx.turn > 1 and self._is_closing(text):
                self.ctx.ended = True
                reply = self.phrase("goodbye")
            return await self._finish_turn(text, TurnResult(reply=reply, guard="unsupported_area"))

        # Guard 3: an FAQ about a named business ("Spice Garden lo parking unda?") → answer from its data.
        if (faq := await self._faq_guard(text)) is not None:
            return await self._finish_turn(text, faq)

        # Guard 4: never take OTPs / PINs / card numbers (already redacted above).
        prefix = ""
        if secret:
            prefix = self.phrase("never_ask_otp") + " "
            self.history.append(
                {
                    "role": "user",
                    "content": "<note>The caller mentioned a secret (OTP/PIN/card). It was redacted. "
                    "Never ask for it.</note>",
                }
            )

        self.history.append({"role": "user", "content": text})
        # A plain "yes" to a waiting read-back: code books it (no LLM call, no paraphrase).
        if self._is_plain_yes(text):
            result = await self._confirm_now()
        elif self._is_yes_words(text) and self.ctx.pending is None and (proposal := await self._propose_from_slots()):
            # The LLM read details back without propose_*: rebuild the real read-back from code.
            result = proposal
        elif (
            new_info
            and self.ctx.pending is None
            and not self.ctx.booking_id
            and (proposal := await self._propose_from_slots())
        ):
            # Every detail is known from the caller's own words: code reads back, no LLM round-trip.
            result = proposal
        else:
            result = await self._llm_loop()
        result.reply = (prefix + result.reply).strip()
        if prefix:
            result.guard = "secret_redacted"
        return await self._finish_turn(None, result)

    async def end(self) -> dict[str, Any]:
        outcome = self.ctx.outcome_json()
        lat = self.ctx.latency_summary()
        summary = self._summary()
        if self.ctx.call_id:
            await self.svc.store.execute(
                """update public.calls set ended_at = now(), language = %(lang)s, services_used = %(svc)s,
                          transcript = %(tr)s, outcome_json = %(out)s, tool_timeline = %(tl)s,
                          latency_json = %(lat)s, summary = %(sum)s where call_id = %(c)s""",
                {
                    "lang": outcome["language"],
                    "svc": [self.ctx.service] if self.ctx.service else [],
                    "tr": _jsonb(self.ctx.transcript),
                    "out": _jsonb(outcome),
                    "tl": _jsonb(self.tools.timeline),
                    "lat": _jsonb(
                        {
                            **lat,
                            "per_step_ms": self.ctx.llm_ms,
                            "tokens_in": self.ctx.tokens_in,
                            "tokens_out": self.ctx.tokens_out,
                        }
                    ),
                    "sum": summary,
                    "c": self.ctx.call_id,
                },
            )
            await self.emit(
                "call_ended", {"outcome": outcome["outcome"], "duration_s": 0, "booking_id": self.ctx.booking_id}
            )
        return outcome

    # -- internals -------------------------------------------------------------

    async def _llm_loop(self) -> TurnResult:
        out = TurnResult(reply="")
        for _ in range(MAX_STEPS):
            reply = await self.llm.complete(
                [{"role": "system", "content": self._system_prompt()}, *self.history[-HISTORY_TURNS:]]
            )
            self._track(reply)
            self.history.append({"role": "assistant", "content": reply.raw})
            if reply.parse_error and not reply.say:
                self.history.append(
                    {
                        "role": "user",
                        "content": "<note>Your last reply was not one valid JSON object. "
                        'Reply again with {"say": ..., "actions": [...]}.</note>',
                    }
                )
                continue
            say = self._verified_amounts(reply.say)
            if not reply.actions:
                out.reply = say
                break
            if say:
                out.fillers.append(say)
            results = await self._run_actions(reply, out)
            self.history.append(
                {
                    "role": "user",
                    "content": "<tool_results>"
                    + json.dumps(results, ensure_ascii=False, default=str)
                    + "</tool_results>",
                }
            )
            forced = [
                r["result"]["force_say"]
                for r in results
                if isinstance(r.get("result"), dict) and r["result"].get("force_say")
            ]
            if forced:  # code-written line (e.g. the booking read-back): say it verbatim, no LLM paraphrase
                out.reply = forced[-1]
                self.history.append(
                    {"role": "assistant", "content": json.dumps({"say": out.reply, "actions": []}, ensure_ascii=False)}
                )
                break
            spoken = [
                r["result"].get("say_this")
                for r in results
                if isinstance(r.get("result"), dict) and r["result"].get("say_this")
            ]
            if self.ctx.emergency and spoken:  # the LLM-path emergency: say the fixed line, nothing else
                out.reply = spoken[-1]
                break
            if self.ctx.ended:
                out.reply = spoken[-1] if spoken else (reply.say or self.phrase("goodbye"))
                break
        else:
            out.reply = self.phrase("didnt_catch_that")
        if not out.reply:
            out.reply = self.phrase("didnt_catch_that")
        return out

    def _verified_amounts(self, text: str) -> str:
        """Drop sentences where the LLM states a ₹ amount no tool returned in this call (it once
        read back "fee 1000 rupaye" for a ₹650 doctor). Fees and deposits come from code."""
        if not text or not MONEY_RE.search(text):
            return text
        # ensure_ascii=False: "₹300" must stay "₹300", not "\u20b9300" (which reads as 9300).
        dumped = json.dumps(self.tools.timeline, default=str, ensure_ascii=False)
        known = {int(n) for n in re.findall(r"\d+", dumped)} | self._catalogue_amounts()
        kept = []
        for sentence in re.split(r"(?<=[.?!।])\s+", text):
            amounts = {int(a.replace(",", "")) for m in MONEY_RE.finditer(sentence) for a in m.groups() if a}
            if amounts <= known:
                kept.append(sentence)
        if len(kept) < len(re.split(r"(?<=[.?!।])\s+", text)):
            log.warning("dropped an unverified amount from the LLM reply: %r", text)
        return " ".join(kept)

    def _catalogue_amounts(self) -> set[int]:
        """₹ facts of the business in this call: deposit and price for two, or its doctors' fees."""
        biz = str(self.ctx.slots.get("business_id") or "")
        amounts: set[int] = set()
        for r in self.catalog.restaurants:
            if r.restaurant_id == biz:
                amounts |= {r.booking_rules.deposit_inr, r.price_for_two_inr}
        # Once a doctor is chosen, only their fee (T29: "fee 900" was another doctor's fee).
        doc = self.ctx.slots.get("doctor_id")
        amounts |= {
            d.consultation_fee_inr
            for d in self.catalog.doctors
            if (d.doctor_id == doc if doc else d.hospital_id == biz)
        }
        return amounts

    def _is_yes_words(self, text: str) -> bool:
        words = re.findall(r"[a-z]+", text.lower())
        return 0 < len(words) <= 6 and not (set(words) & NO_WORDS) and all(w in YES_WORDS for w in words)

    def caller_said_yes(self) -> bool:
        """The caller's latest turn agrees: a yes word and nothing negative ("Haan, confirm kar dijiye")."""
        last = self.last_caller_text()
        words = set(re.findall(r"[a-z]+", last.lower()))
        native_yes = any(w in last for w in ("అవును", "సరే", "హాఁ", "हाँ", "हां", "ठीक"))
        return bool(words & CORE_YES or native_yes) and not (words & NO_WORDS)

    def _is_plain_yes(self, text: str) -> bool:
        p = self.ctx.pending
        return p is not None and p.turn < self.ctx.turn and self._is_yes_words(text)

    def _is_closing(self, text: str) -> bool:
        t = norm(text)
        return any(w in t.split() for w in ("thanks", "thank", "parledu", "bye", "shukriya", "dhanyavad", "ok"))

    def _other_area(self, text: str) -> str | None:
        t = f" {norm(text)} "
        demo = {norm(x) for a in self.catalog.areas for x in [a.name_en, *a.aliases] if len(x) >= 4}
        if any(f" {x} " in t for x in demo):
            return None
        nearby = {norm(n): n for a in self.catalog.areas for n in a.nearby_unsupported_areas}
        for key in sorted({*nearby, *OTHER_AREAS}, key=len, reverse=True):
            if f" {key} " in t:
                return nearby.get(key, key.title())
        return None

    async def _extract(self, text: str) -> bool:
        """Read facts from the caller's words into slots. Returns True if anything new was learned."""
        before = dict(self.ctx.slots)
        if party := parse_party(text):
            await self.set_slot("party_size", party)
        last_vaani = next(
            (t["text"].lower() for t in reversed(self.ctx.transcript[:-1]) if t["speaker"] == "vaani"), ""
        )
        asked = any(w in last_vaani for w in ("peru", "naam", "name"))
        if (name := parse_name(text, asked_for_name=asked)) and not is_entity_name(name, self.catalog):
            await self.set_slot("name", name)
        biz = find_business(text, self.catalog)
        doc = find_doctor_named(text, self.catalog, getattr(biz, "hospital_id", None))
        if (spec := find_speciality_phrase(text, self.catalog)) and self.ctx.service in (None, "hospital"):
            # "pallu noppi", "skin doctor": a health need → hospital agent, decided in code.
            await self._route_if_needed("hospital")
            await self.set_slot("speciality", spec)
        if biz is not None and hasattr(biz, "hospital_id"):
            cur = self.ctx.slots.get("doctor_id")
            if cur and not any(d.doctor_id == cur and d.hospital_id == biz.hospital_id for d in self.catalog.doctors):
                await self.set_slot("doctor_id", None)  # caller moved to another hospital
        if biz is not None:
            is_rest = hasattr(biz, "restaurant_id")
            await self._route_if_needed("restaurant" if is_rest else "hospital")
            await self.set_slot("business_id", biz.restaurant_id if is_rest else biz.hospital_id)  # type: ignore[union-attr]
            await self.set_slot("area_id", biz.area_id)
            self.ctx.named_turn = self.ctx.turn
        if doc is not None:
            await self._route_if_needed("hospital")
            for k, v in (
                ("doctor_id", doc.doctor_id),
                ("business_id", doc.hospital_id),
                ("speciality", doc.speciality),
            ):
                await self.set_slot(k, v)
            area = next(h.area_id for h in self.catalog.hospitals if h.hospital_id == doc.hospital_id)
            await self.set_slot("area_id", area)
            self.ctx.named_turn = self.ctx.turn
        if self.ctx.heard_day:
            await self.set_slot("date", self.ctx.heard_day)
        if self.ctx.heard_time:
            await self.set_slot("time", self.ctx.heard_time)
        self._infer_doctor()
        return self.ctx.slots != before

    def _infer_doctor(self) -> None:
        """Hospital + speciality known but no doctor: if only one doctor there fits, that's the one."""
        sl = self.ctx.slots
        biz, spec = str(sl.get("business_id") or ""), sl.get("speciality")
        if sl.get("doctor_id") or not biz.startswith("h_") or not spec:
            return
        docs = [d for d in self.catalog.doctors if d.hospital_id == biz and d.speciality == spec]
        if sl.get("time") and len(docs) > 1:
            from backend.catalog.models import parse_range, to_minutes

            t = to_minutes(sl["time"])
            docs = [d for d in docs if any(lo <= t < hi for lo, hi in (parse_range(r) for r in d.schedule.values()))]
        if len(docs) == 1:
            sl["doctor_id"] = docs[0].doctor_id

    async def _route_if_needed(self, service: str) -> None:
        if self.ctx.service is None:
            self.ctx.service = service  # type: ignore[assignment]
            self.ctx.node = service
            await self.emit("agent_switched", {"from": "router", "to": service})

    async def _faq_guard(self, text: str) -> TurnResult | None:
        words = set(norm(text).split())
        biz = find_business(text, self.catalog)
        if biz is None or self.ctx.pending is not None:
            return None
        topical = (
            bool(words & FAQ_WORDS)
            or bool(words & KIDS_WORDS)
            or ("emergency" in words and bool(words & {"24", "ghante", "hours", "open", "khula", "untundi"}))
        )
        if not topical or (words & BOOKING_WORDS):
            return None
        from backend.tools import run_tool

        biz_id = getattr(biz, "restaurant_id", None) or getattr(biz, "hospital_id", "")
        r = await run_tool(
            self.tools, "answer_faq", {"business_id": biz_id, "question": text, "lang": self.ctx.language}
        )
        if not r.get("answer"):
            return None
        self.ctx.faq_answered = True
        reply = f"{r['answer']} {self.phrase('anything_else')}"
        self.history.append({"role": "user", "content": text})
        self.history.append(
            {"role": "assistant", "content": json.dumps({"say": reply, "actions": []}, ensure_ascii=False)}
        )
        return TurnResult(reply=reply, guard="faq")

    async def _propose_from_slots(self) -> TurnResult | None:
        from backend.flows.nodes import propose_appointment, propose_booking

        sl = self.ctx.slots
        if self.ctx.emergency:
            return None
        if (
            self.ctx.service == "restaurant"
            and str(sl.get("business_id") or "").startswith("r_")
            and all(sl.get(k) for k in ("date", "time", "party_size", "name"))
        ):
            res, _ = await propose_booking(
                self,
                {
                    "restaurant": sl["business_id"],
                    "date": sl["date"],
                    "time": sl["time"],
                    "party_size": sl["party_size"],
                    "name": sl["name"],
                },
            )
        elif self.ctx.service == "hospital" and all(sl.get(k) for k in ("doctor_id", "date", "time", "name")):
            res, _ = await propose_appointment(
                self, {"doctor": sl["doctor_id"], "date": sl["date"], "time": sl["time"], "name": sl["name"]}
            )
        else:
            return None
        if not res.get("force_say"):
            if res.get("error") in ("SLOT_FULL", "SLOT_TAKEN", "PARTY_TOO_LARGE", "BLOCKED"):
                # Tell the LLM so it offers the alternatives in the caller's language.
                self.history.append(
                    {
                        "role": "user",
                        "content": "<tool_results>"
                        + json.dumps([{"tool": "propose", "result": res}], ensure_ascii=False)
                        + "</tool_results>",
                    }
                )
                self.ctx.heard_time = None
                self.ctx.slots["time"] = None
                return await self._llm_loop()
            return None
        reply = str(res["force_say"])
        self.history.append(
            {"role": "assistant", "content": json.dumps({"say": reply, "actions": []}, ensure_ascii=False)}
        )
        return TurnResult(reply=reply, actions=[{"tool": "propose_from_slots", "args": {}, "ok": True}])

    async def _confirm_now(self) -> TurnResult:
        from backend.flows.nodes import confirm_booking

        res, _ = await confirm_booking(self, {})
        out = TurnResult(reply="", actions=[{"tool": "confirm_booking", "args": {}, "ok": bool(res.get("ok"))}])
        if res.get("ok"):
            done = self.phrase("booking_done_whatsapp_sent").replace("{booking_id}", str(res["booking_id"]))
            due = int(res.get("deposit_inr") or 0) or int(res.get("fee_inr") or 0)
            extra = {
                "te": " Payment link (test) kuda WhatsApp lo undi.",
                "hi": " Payment ka test link bhi WhatsApp pe hai.",
                "en": " The test-mode payment link is on WhatsApp too.",
            }
            out.reply = done + (extra.get(self.ctx.language, extra["en"]) if due else "")
        else:
            # Slot vanished between read-back and yes (another caller): let the LLM offer alternatives.
            self.history.append(
                {
                    "role": "user",
                    "content": "<tool_results>"
                    + json.dumps([{"tool": "confirm_booking", "result": res}], ensure_ascii=False)
                    + "</tool_results>",
                }
            )
            return await self._llm_loop()
        self.history.append(
            {"role": "assistant", "content": json.dumps({"say": out.reply, "actions": []}, ensure_ascii=False)}
        )
        return out

    async def _run_actions(self, reply: LLMReply, out: TurnResult) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for action in reply.actions[:MAX_ACTIONS_PER_STEP]:
            fns = functions_for(self.ctx.node)
            spec: FunctionSpec | None = fns.get(action.tool)
            if spec is None:
                res: dict[str, Any] = {"ok": False, "error": "UNKNOWN_FUNCTION", "allowed": sorted(fns)}
                nxt = None
            else:
                try:
                    res, nxt = await spec.handler(self, action.args)
                except Exception as e:  # noqa: BLE001 - a bad argument must never crash the call
                    res, nxt = {"ok": False, "error": "FUNCTION_FAILED", "message": f"{type(e).__name__}: {e}"}, None
            if nxt and nxt in NODES:
                self.ctx.node = nxt
            results.append({"tool": action.tool, "result": res})
            out.actions.append({"tool": action.tool, "args": action.args, "ok": bool(res.get("ok", True))})
            if self.ctx.ended or self.ctx.emergency:
                break
        return results

    def _track(self, reply: LLMReply) -> None:
        self.ctx.llm_ms.append(reply.ms)
        self.ctx.tokens_in += reply.prompt_tokens
        self.ctx.tokens_out += reply.completion_tokens

    async def _finish_turn(self, _: str | None, result: TurnResult) -> TurnResult:
        if result.guard == "emergency":
            self.history.append(
                {"role": "assistant", "content": json.dumps({"say": result.reply, "actions": []}, ensure_ascii=False)}
            )
        await self._log("vaani", result.reply, self.ctx.language)
        return result

    async def _log(self, speaker: str, text: str, lang: str) -> None:
        self.ctx.say(speaker, text, lang)  # type: ignore[arg-type]
        await self.emit("transcript", {"speaker": speaker, "lang": lang, "text": text, "final": True})

    def _summary(self) -> str:
        o = self.ctx.outcome
        s = self.ctx.slots
        lang_name = LANG_NAMES.get(self.ctx.language, self.ctx.language)
        first = f"{lang_name} {self.ctx.service or 'unrouted'} call → {o.replace('_', ' ')}"
        if self.ctx.booking_id:
            first += f" ({self.ctx.booking_id})"
        detail = ", ".join(f"{k}={v}" for k, v in s.items() if v and k != "name")
        return f"{first}.\n{detail or 'No details collected.'}"

    def _system_prompt(self) -> str:
        node = NODES[self.ctx.node]
        lang = self.ctx.language
        service = self.ctx.service or "router"
        fns = functions_for(self.ctx.node)
        fn_lines = "\n".join(f"- {f.name}({_params(f)}): {f.description}" for f in fns.values())
        today = today_ist()
        cal = "\n".join(
            f"- {(today + timedelta(days=i)).isoformat()} {(today + timedelta(days=i)).strftime('%a')}"
            + (f" = {' / '.join(DAY_WORDS[i])}" if i in DAY_WORDS else f" = in {i} days")
            for i in range(7)
        )
        known = {k: v for k, v in self.ctx.slots.items() if v is not None}
        pending = self.ctx.pending.readback if self.ctx.pending else None
        examples = prompts.load(f"examples_{service}.md", lang) if service in ("restaurant", "hospital") else ""
        parts = [
            prompts.load("rules.md"),
            f"## Language\nReply in {LANG_NAMES.get(lang, lang)}, romanised, the way people in Hyderabad talk.\n"
            + prompts.load("style.md", lang),
            f"## Current stage: {node.name}\n{node.task}",
            f"## Functions you can call now\n{fn_lines}",
            f"## Calendar (bookable days)\n{cal}",
            f"## Known so far\n{json.dumps(known, ensure_ascii=False)}"
            + (
                f"\nWaiting for the caller to confirm this read-back: {json.dumps(pending, ensure_ascii=False)}"
                if pending
                else ""
            ),
            f"## Example calls\n{examples}" if examples else "",
        ]
        return "\n\n".join(p for p in parts if p)


def _params(f: FunctionSpec) -> str:
    """'area, date, party_size, time?' — optional params get a '?'."""
    return ", ".join(k if k in f.required else k + "?" for k in f.properties)


def _jsonb(value: Any) -> Any:
    from psycopg.types.json import Jsonb

    return Jsonb(value)
