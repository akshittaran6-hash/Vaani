"""answer_faq: answer only from the business's own FAQs, in the caller's language."""

from __future__ import annotations

from typing import Literal

from rapidfuzz import fuzz

from backend.catalog.models import Faq, Hospital, Restaurant
from backend.text import norm
from backend.tools.base import Args, Result, ToolContext, ToolError, tool

# Topic keywords in English + romanised Telugu/Hindi (+ a few script forms), matched
# against both the caller's question and each FAQ's question.
TOPICS: dict[str, set[str]] = {
    "parking": {"parking", "park", "car", "bike", "vehicle", "gaadi", "పార్కింగ్", "पार्किंग"},
    "timings": {
        "timing",
        "timings",
        "time",
        "open",
        "close",
        "closing",
        "hours",
        "opd",
        "samayam",
        "kab",
        "baje",
        "eppudu",
        "tereechi",
        "sunday",
        "ravivar",
        "aadivaram",
        "adivaram",
    },
    "veg": {"veg", "vegetarian", "non-veg", "nonveg", "shakahari", "shakahaari", "meat", "chicken", "jain", "menu"},
    "access": {"wheelchair", "accessible", "access", "ramp", "lift", "divyang", "వీల్‌చైర్", "व्हीलचेयर"},
    "lab": {"lab", "laboratory", "blood test", "tests", "ల్యాబ్", "लैब"},
    "fee": {"fee", "fees", "consultation", "charge", "charges", "kitni fee", "entha fee"},
    "kids": {
        "kids",
        "kid",
        "child",
        "children",
        "baby",
        "pillalu",
        "pillala",
        "bachche",
        "bachchon",
        "bachon",
        "family",
    },
    "deposit": {"deposit", "advance", "pay", "payment", "booking amount", "paisa", "dabbulu"},
    "insurance": {"insurance", "cashless", "claim", "policy", "beema", "bima"},
    "walkin": {"walk-in", "walkin", "walk", "without appointment", "direct", "appointment lekunda", "bina appointment"},
    "emergency": {"emergency", "24x7", "24", "casualty", "ambulance", "raatri", "night"},
}
MIN_SCORE = 55


class AnswerFaqArgs(Args):
    business_id: str
    question: str
    lang: Literal["te", "hi", "en"] | None = None


def _topics(text: str) -> set[str]:
    words = f" {norm(text)} "
    return {t for t, kws in TOPICS.items() if any(f" {k} " in words for k in kws)}


def _score(question: str, faq: Faq) -> float:
    shared = _topics(question) & _topics(faq.q)
    return (60 if shared else 0) + 0.4 * fuzz.token_set_ratio(norm(question), norm(faq.q))


@tool("answer_faq", AnswerFaqArgs, "Answer a question about one business from its FAQs only.")
async def answer_faq(ctx: ToolContext, a: AnswerFaqArgs) -> tuple[Result, str]:
    businesses: dict[str, Restaurant | Hospital] = {r.restaurant_id: r for r in ctx.catalog.restaurants}
    businesses |= {h.hospital_id: h for h in ctx.catalog.hospitals}
    biz = businesses.get(a.business_id)
    if biz is None:
        raise ToolError("UNKNOWN_BUSINESS", f"No business {a.business_id}")
    lang = a.lang or ctx.language
    scored = sorted(((_score(a.question, f), f) for f in biz.faqs), key=lambda x: -x[0])
    if not scored or scored[0][0] < MIN_SCORE:
        return {"unknown": True, "business_id": a.business_id}, f"FAQ for {biz.name}: no answer on file"
    faq = scored[0][1]
    answer = {"te": faq.a_te, "hi": faq.a_hi}.get(lang, faq.a_en)
    return {"answer": answer, "lang": lang, "question_matched": faq.q}, f"Answered FAQ for {biz.name}: “{faq.q}”"
