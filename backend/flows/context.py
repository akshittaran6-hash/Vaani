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
            # Text mode has no audio: STT/TTS stay 0 until Phase 4.
            "latency_ms": {
                "stt": 0,
                "llm_first_token": lat["llm_median"],
                "tts_first_audio": 0,
                "turn_median": lat["llm_median"],
            },
        }
