"""Scoring one replayed test call against data/test_calls.json `expected` (EVAL.md metrics)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from backend.catalog.models import TestCall
from backend.flows.context import CallContext

LANG_ORDER = ("te-en", "hi-en", "en-IN")

# metric key → (label, EVAL.md target)
METRICS: dict[str, tuple[str, str]] = {
    "booking": ("Booking accuracy (business, doctor, day, time, party all correct)", "≥ 85–90%"),
    "top3": ("Expected business in top 3", "≥ 90%"),
    "unsupported": ("Unsupported area handled", "100%"),
    "emergency": ("Emergency → 108/112, no booking", "100%"),
    "slot_full": ("Slot full → 2 nearest offered", "≥ 90%"),
    "faq": ("FAQ answered from the business's data", "report"),
    "outcome": ("Outcome matches expected", "report"),
    "passed": ("Call passed (outcome + booking)", "report"),
}


@dataclass
class CaseResult:
    test_id: str
    service: str
    language_mix: str
    scenario: str
    expected_outcome: str
    actual_outcome: str
    checks: dict[str, bool | None] = field(default_factory=dict)
    booking: dict[str, Any] | None = None
    reasons: list[str] = field(default_factory=list)
    llm_calls: int = 0
    llm_ms: list[int] = field(default_factory=list)
    llm_models: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    transcript: list[dict[str, Any]] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return bool(self.checks.get("passed"))

    def to_json(self) -> dict[str, Any]:
        return {**asdict(self), "passed": self.passed}


def score(case: TestCall, ctx: CallContext, booking: dict[str, Any] | None, today: date) -> CaseResult:
    e = case.expected
    res = CaseResult(case.test_id, case.service, case.language_mix, case.scenario, e.outcome, ctx.outcome)
    c = res.checks

    actual = None
    if booking:
        actual = {
            "business_id": booking["business_id"],
            "doctor_id": booking.get("doctor_id"),
            "day_offset": (booking["date"] - today).days,
            "time": booking["time"].strftime("%H:%M"),
            "party_size": booking.get("party_size"),
        }
        res.booking = actual

    c["outcome"] = ctx.outcome == e.outcome
    if not c["outcome"]:
        res.reasons.append(f"outcome {ctx.outcome} ≠ expected {e.outcome}")

    if e.outcome == "booked":
        want = {"business_id": e.business_id, "day_offset": e.day_offset, "time": e.time}
        if case.service == "restaurant":
            want["party_size"] = e.party_size
        else:
            want["doctor_id"] = e.doctor_id
        if actual is None:
            c["booking"] = False
            res.reasons.append("no booking made")
        else:
            wrong = {k: (actual.get(k), v) for k, v in want.items() if actual.get(k) != v}
            c["booking"] = not wrong
            for k, (got, exp) in wrong.items():
                res.reasons.append(f"{k}: got {got}, expected {exp}")
    elif actual is not None:
        res.reasons.append(f"booked {actual} but expected {e.outcome}")

    # Top-3 only counts when the agent actually searched (callers sometimes name the place).
    c["top3"] = (e.business_id in ctx.search_result_ids) if (e.business_id and ctx.search_result_ids) else None
    if c["top3"] is False:
        res.reasons.append(f"{e.business_id} not in search results")

    c["unsupported"] = None
    if case.scenario == "unsupported_area":
        ok = bool(ctx.unsupported_heard) and (e.outcome == "booked" or actual is None)
        c["unsupported"] = ok
        if not ok:
            res.reasons.append(
                "unsupported area not detected" if not ctx.unsupported_heard else "booked in an unsupported area"
            )

    c["emergency"] = None
    if case.scenario == "emergency":
        c["emergency"] = ctx.emergency and actual is None
        if not c["emergency"]:
            res.reasons.append("emergency not redirected")

    c["slot_full"] = None
    if case.scenario == "slot_full":
        c["slot_full"] = len(ctx.nearest_offered) >= 2
        if not c["slot_full"]:
            res.reasons.append("2 nearest times not offered")

    c["faq"] = ctx.faq_answered if case.scenario == "faq" else None

    c["passed"] = bool(c["outcome"]) and c.get("booking") is not False and actual_ok_for_non_booking(e.outcome, actual)
    res.llm_calls = len(ctx.llm_ms)
    res.llm_ms = list(ctx.llm_ms)
    res.llm_models = list(ctx.llm_models)
    res.tokens_in, res.tokens_out = ctx.tokens_in, ctx.tokens_out
    res.transcript = list(ctx.transcript)
    return res


def actual_ok_for_non_booking(expected_outcome: str, actual: dict[str, Any] | None) -> bool:
    return expected_outcome == "booked" or actual is None


def summarize(results: list[CaseResult]) -> dict[str, dict[str, tuple[int, int]]]:
    """metric → language_mix (+ 'all') → (hits, n)."""
    out: dict[str, dict[str, tuple[int, int]]] = {}
    for key in METRICS:
        per: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in results:
            v = r.checks.get(key)
            if v is None:
                continue
            for bucket in (r.language_mix, "all"):
                per[bucket][0] += int(bool(v))
                per[bucket][1] += 1
        out[key] = {b: (h, n) for b, (h, n) in per.items()}
    return out


def pct(h: int, n: int) -> str:
    return f"{h}/{n} ({round(100 * h / n)}%)" if n else "—"


def markdown_table(summary: dict[str, dict[str, tuple[int, int]]]) -> str:
    lines = ["| Metric | Target | te-en | hi-en | en-IN | All |", "|---|---|---|---|---|---|"]
    for key, (label, target) in METRICS.items():
        row = summary.get(key, {})
        cells = [pct(*row.get(b, (0, 0))) for b in (*LANG_ORDER, "all")]
        lines.append(f"| {label} | {target} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
