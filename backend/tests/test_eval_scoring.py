"""Eval scoring on hand-built results (no LLM, no DB)."""

from __future__ import annotations

from datetime import date, time

from backend.catalog.models import Catalog
from backend.eval.scoring import markdown_table, score, summarize
from backend.flows.context import CallContext

TODAY = date(2026, 11, 22)


def _ctx(**kw: object) -> CallContext:
    c = CallContext(phone="+91")
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_booked_call_scores_every_field(catalog: Catalog) -> None:
    t01 = next(t for t in catalog.test_calls if t.test_id == "T01")
    booking = {
        "business_id": "r_jh_01",
        "doctor_id": None,
        "date": date(2026, 11, 23),
        "time": time(20, 30),
        "party_size": 6,
    }
    ctx = _ctx(booking_id="VN-1", search_result_ids=["r_jh_01", "r_jh_02"], nearest_offered=["19:30", "20:30"])
    r = score(t01, ctx, booking, TODAY)
    assert r.passed and r.checks["booking"] and r.checks["top3"] and r.checks["slot_full"]

    wrong = {**booking, "time": time(19, 30)}
    r2 = score(t01, ctx, wrong, TODAY)
    assert not r2.passed and "time: got 19:30, expected 20:30" in r2.reasons


def test_emergency_and_unsupported(catalog: Catalog) -> None:
    t28 = next(t for t in catalog.test_calls if t.test_id == "T28")
    assert score(t28, _ctx(emergency=True), None, TODAY).passed
    booked = {
        "business_id": "h_gb_01",
        "doctor_id": "d_gb_01_derm_1",
        "date": date(2026, 11, 23),
        "time": time(11, 0),
        "party_size": None,
    }
    assert not score(t28, _ctx(emergency=True), booked, TODAY).checks["emergency"]

    t04 = next(t for t in catalog.test_calls if t.test_id == "T04")
    r = score(t04, _ctx(unsupported_heard="Kukatpally"), None, TODAY)
    assert r.passed and r.checks["unsupported"]


def test_summary_table_splits_by_language(catalog: Catalog) -> None:
    calls = {t.test_id: t for t in catalog.test_calls}
    results = [
        score(calls["T28"], _ctx(emergency=True), None, TODAY),  # te-en
        score(calls["T29"], _ctx(), None, TODAY),  # hi-en, missed emergency
    ]
    summary = summarize(results)
    assert summary["emergency"]["te-en"] == (1, 1) and summary["emergency"]["hi-en"] == (0, 1)
    assert summary["emergency"]["all"] == (1, 2)
    table = markdown_table(summary)
    assert "| Emergency → 108/112, no booking | 100% | 1/1 (100%) | 0/1 (0%) | — | 1/2 (50%) |" in table
