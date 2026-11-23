"""CallContext: everything Vaani knows about one call. It carries across node switches
(router → restaurant / hospital), like Pipecat Flows' flow_manager.state."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.clock import iso_ts

Service = Literal["restaurant", "hospital"]
SLOT_NAMES = ("area_id", "business_id", "doctor_id", "speciality", "date", "time", "party_size", "name")


@dataclass
class Pending:
    """A read-back waiting for the caller's yes. Booking needs it from an EARLIER turn."""

    service: Service
    tool: Literal["book_table", "book_appointment"]
    args: dict[str, Any]
    readback: dict[str, Any]
    turn: int


@dataclass
class CallContext:
    phone: str
    channel: Literal["phone", "web"] = "web"
    call_id: str | None = None
    language: str = "te"
    languages_seen: list[str] = field(default_factory=list)
    service: Service | None = None
    node: str = "router"
    slots: dict[str, Any] = field(default_factory=lambda: dict.fromkeys(SLOT_NAMES))
    pending: Pending | None = None
    booking_id: str | None = None
    turn: int = 0
    ended: bool = False
    started_at: str = field(default_factory=iso_ts)

    # What happened, for the outcome JSON and the eval.
    emergency: bool = False
    self_harm: bool = False  # the caller mentioned self-harm (counts as an emergency: no booking)
    transferred: bool = False
    unsupported_heard: str | None = None
    offered_alternatives: bool = False
    nearest_offered: list[str] = field(default_factory=list)
    faq_answered: bool = False
    no_availability: bool = False
    search_result_ids: list[str] = field(default_factory=list)
    # Latest day/time the CALLER said (parsed in code); beats the LLM's arguments.
    heard_day: str | None = None
    heard_time: str | None = None
    named_turn: int = -1  # turn in which the caller last named a business/doctor (code wins that turn)

    transcript: list[dict[str, Any]] = field(default_factory=list)
    llm_ms: list[int] = field(default_factory=list)
    llm_models: list[str] = field(default_factory=list)  # which model answered each step
    # Voice calls: one row per turn {turn, stt, llm_first_token, tts_first_audio, turn_total} (ms).
    voice_turns: list[dict[str, int]] = field(default_factory=list)
    barge_in_ms: list[int] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0

    def say(self, speaker: Literal["caller", "vaani"], text: str, lang: str) -> None:
        self.transcript.append({"ts": iso_ts(), "speaker": speaker, "lang": lang, "text": text})
        if speaker == "caller" and lang not in self.languages_seen:
            self.languages_seen.append(lang)

    # -- outcome ---------------------------------------------------------------

    @property
    def outcome(self) -> str:
        if self.emergency:
            return "redirected_emergency"
        if self.booking_id:
            return "booked"
        if self.transferred:
            return "transferred"
        if self.unsupported_heard and not self.slots.get("business_id"):
            return "declined_unsupported_area"
        if self.offered_alternatives:
            return "offered_alternatives"
        if self.faq_answered:
            return "answered_faq"
        if self.no_availability:
            return "no_availability"
        return "abandoned"

    @property
    def intent(self) -> str:
        return {
            "redirected_emergency": "emergency",
            "declined_unsupported_area": "unsupported_area",
            "answered_faq": "info",
            "transferred": "human",
            "abandoned": "other",
        }.get(self.outcome, "book")

    def latency_summary(self) -> dict[str, int]:
        if not self.llm_ms:
            return {"llm_median": 0, "llm_p95": 0, "llm_calls": 0}
        ordered = sorted(self.llm_ms)
        p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
        return {"llm_median": round(statistics.median(ordered)), "llm_p95": p95, "llm_calls": len(ordered)}

    def outcome_json(self) -> dict[str, Any]:
        """docs/CONTRACTS.md §5 shape."""
        langs = list(self.languages_seen) or [self.language]
        if "en" not in langs and langs != ["en"]:
            langs.append("en")  # te-en / hi-en code-mixing
        lat = self.latency_summary()
        return {
            "call_id": self.call_id,
            "language": langs,
            "service": self.service,
            "intent": self.intent,
            "slots": dict(self.slots),
            "outcome": self.outcome,
            "booking_id": self.booking_id,
            # Voice calls: medians over the turns. Text mode (eval/CLI) has no audio, so STT/TTS stay 0.
            "latency_ms": self.voice_latency_medians()
            or {"stt": 0, "llm_first_token": lat["llm_median"], "tts_first_audio": 0, "turn_median": lat["llm_median"]},
        }

    def voice_latency_medians(self) -> dict[str, int] | None:
        if not self.voice_turns:
            return None

        def med(key: str) -> int:
            vals = [t[key] for t in self.voice_turns if t.get(key) is not None]
            return round(statistics.median(vals)) if vals else 0

        return {
            "stt": med("stt"),
            "llm_first_token": med("llm_first_token"),
            "tts_first_audio": med("tts_first_audio"),
            "turn_median": med("turn_total"),
        }
