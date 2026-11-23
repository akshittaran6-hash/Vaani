"""REST endpoints (CONTRACTS.md §3) through the ASGI app."""

from __future__ import annotations

import json

import httpx
import pytest

from backend import partners
from backend.api.deps import Services
from backend.messaging import MockMessenger
from backend.payments import sign
from backend.tests.conftest import CALLER, WEBHOOK_SECRET, day
from backend.tools import run_tool

pytestmark = pytest.mark.db


def pc(svc: Services, business_id: str) -> dict[str, str]:
    return {"X-Partner-Passcode": partners.passcode(svc.settings.partner_passcode_secret, business_id)}


async def call_booking(svc: Services, tool: str, args: dict[str, object]) -> tuple[str, str]:
    call_id = await svc.store.start_call("phone", CALLER)
    r = await run_tool(svc.tool_context(call_id=call_id, phone=CALLER, language="te"), tool, args)
    assert r["ok"], r
    return str(r["booking_id"]), call_id


async def test_health(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["db"] is True


async def test_businesses(client: httpx.AsyncClient) -> None:
    rest = (await client.get("/api/businesses", params={"area": "jubilee_hills", "type": "restaurant"})).json()
    assert len(rest) == 5 and all(b["type"] == "restaurant" and "phone" not in b for b in rest)
    allb = (await client.get("/api/businesses")).json()
    assert len(allb) == 20
    hosp = next(b for b in allb if b["id"] == "h_gb_01")
    assert hosp["doctors"] and hosp["slug"] == "navaniti-hospital-gachibowli"


async def test_slot_endpoints(client: httpx.AsyncClient) -> None:
    r = (await client.get("/api/restaurants/r_jh_01/slots", params={"date": day(1).isoformat()})).json()
    s = {x["time"]: x for x in r["slots"]}
    assert s["20:00"]["free_tables"] == 0 and s["20:00"]["total_tables"] == 10
    blocked = (await client.get("/api/restaurants/r_jh_02/slots", params={"date": day(2).isoformat()})).json()
    assert {x["time"]: x for x in blocked["slots"]}["13:00"]["blocked"] is True
    d = (await client.get("/api/doctors/d_gb_02_genmed_1/slots", params={"date": day(2).isoformat()})).json()
    assert d["on_leave"] is True and len(d["slots"]) == 12
    assert (await client.get("/api/restaurants/r_zz_01/slots", params={"date": day(1).isoformat()})).status_code == 404


async def test_booking_status_masks_phone(client: httpx.AsyncClient, services: Services) -> None:
    bid, _ = await call_booking(
        services,
        "book_appointment",
        {"doctor_id": "d_gb_01_derm_1", "date": day(1).isoformat(), "time": "11:00", "name": "Lakshmi"},
    )
    r = (await client.get(f"/api/bookings/{bid}")).json()
    assert r["status"] == "pending_payment" and r["amount_due_inr"] == 600
    assert "phone" not in r and r["phone_masked"] == "+91••••••3210" and CALLER not in json.dumps(r)
    assert (await client.get("/api/bookings/VN-0000")).status_code == 404


async def test_partner_bookings_need_passcode(client: httpx.AsyncClient, services: Services) -> None:
    bid, _ = await call_booking(
        services,
        "book_table",
        {"restaurant_id": "r_jh_01", "date": day(1).isoformat(), "time": "20:30", "party_size": 6, "name": "Pranav"},
    )
    url = "/api/partners/r_jh_01/bookings"
    assert (await client.get(url)).status_code == 403
    assert (await client.get(url, headers={"X-Partner-Passcode": "000000"})).status_code == 403
    rows = (await client.get(url, params={"date": day(1).isoformat()}, headers=pc(services, "r_jh_01"))).json()
    assert [b["booking_id"] for b in rows] == [bid] and rows[0]["language"] == "te" and "phone" not in rows[0]


async def test_patch_booking_status(client: httpx.AsyncClient, services: Services) -> None:
    rid, _ = await call_booking(
        services,
        "book_table",
        {"restaurant_id": "r_jh_01", "date": day(1).isoformat(), "time": "19:30", "party_size": 6, "name": "A"},
    )
    hid, _ = await call_booking(
        services,
        "book_appointment",
        {"doctor_id": "d_gb_01_derm_1", "date": day(1).isoformat(), "time": "12:00", "name": "B"},
    )

    assert (await client.patch(f"/api/bookings/{rid}", json={"status": "arrived"})).status_code == 403
    r = await client.patch(f"/api/bookings/{rid}", json={"status": "arrived"}, headers=pc(services, "r_jh_01"))
    assert r.status_code == 200 and r.json()["status"] == "arrived"
    r = await client.patch(f"/api/bookings/{hid}", json={"status": "arrived"}, headers=pc(services, "h_gb_01"))
    assert r.status_code == 409
    r = await client.patch(f"/api/bookings/{hid}", json={"status": "checked_in"}, headers=pc(services, "h_gb_01"))
    assert r.json()["status"] == "checked_in"

    # Cancel (status page, no passcode) frees the table for the next caller.
    r = await client.patch(f"/api/bookings/{rid}", json={"status": "cancelled"})
    assert r.json()["status"] == "cancelled"
    again, _ = await call_booking(
        services,
        "book_table",
        {"restaurant_id": "r_jh_01", "date": day(1).isoformat(), "time": "19:30", "party_size": 6, "name": "C"},
    )
    assert again


async def test_blocked_slot_is_refused_by_the_ai(client: httpx.AsyncClient, services: Services) -> None:
    """Acceptance test 2 (WEBSITES.md): staff block on the portal → the next booking is refused."""
    body = {"business_id": "r_jh_03", "date": day(1).isoformat(), "time": "21:00", "blocked": True}
    assert (await client.post("/api/slots/block", json=body)).status_code == 403
    r = await client.post("/api/slots/block", json=body, headers=pc(services, "r_jh_03"))
    assert r.json() == {"ok": True, "updated": 1}
    ctx = services.tool_context(phone=CALLER)
    slots = await run_tool(
        ctx,
        "get_restaurant_slots",
        {"restaurant_id": "r_jh_03", "date": day(1).isoformat(), "party_size": 3, "time": "21:00"},
    )
    assert slots["requested_full"] is True
    booked = await run_tool(
        ctx,
        "book_table",
        {"restaurant_id": "r_jh_03", "date": day(1).isoformat(), "time": "21:00", "party_size": 3, "name": "Amit"},
    )
    assert booked["error"] == "BLOCKED"
    # Unblock → bookable again
    await client.post("/api/slots/block", json={**body, "blocked": False}, headers=pc(services, "r_jh_03"))
    assert (
        await run_tool(
            ctx,
            "book_table",
            {"restaurant_id": "r_jh_03", "date": day(1).isoformat(), "time": "21:00", "party_size": 3, "name": "Amit"},
        )
    )["ok"]


async def test_close_for_the_day_and_doctor_blocks(client: httpx.AsyncClient, services: Services) -> None:
    r = await client.post(
        "/api/slots/block",
        json={"business_id": "r_gb_01", "date": day(2).isoformat(), "all_day": True},
        headers=pc(services, "r_gb_01"),
    )
    assert r.json()["updated"] == 10
    slots = await run_tool(
        services.tool_context(),
        "get_restaurant_slots",
        {"restaurant_id": "r_gb_01", "date": day(2).isoformat(), "party_size": 2},
    )
    assert slots["free"] == []

    await call_booking(
        services,
        "book_appointment",
        {"doctor_id": "d_gb_03_ent_1", "date": day(3).isoformat(), "time": "10:15", "name": "N"},
    )
    before = await services.store.fetchrow(
        "select count(*) filter (where status <> 'booked') as open, count(*) filter (where status = 'booked') as booked"
        " from public.doctor_slots where doctor_id = 'd_gb_03_ent_1' and date = %(d)s",
        {"d": day(3)},
    )
    assert before is not None and before["booked"] >= 1
    r = await client.post(
        "/api/slots/block",
        json={"business_id": "h_gb_03", "doctor_id": "d_gb_03_ent_1", "date": day(3).isoformat(), "all_day": True},
        headers=pc(services, "h_gb_03"),
    )
    assert r.json()["updated"] == before["open"]  # booked slots are never touched
    after = await services.store.fetchrow(
        "select count(*) as booked from public.doctor_slots where doctor_id = 'd_gb_03_ent_1' and date = %(d)s and status = 'booked'",
        {"d": day(3)},
    )
    assert after == {"booked": before["booked"]}
    wrong = await client.post(
        "/api/slots/block",
        json={"business_id": "h_gb_01", "doctor_id": "d_gb_03_ent_1", "date": day(3).isoformat(), "all_day": True},
        headers=pc(services, "h_gb_01"),
    )
    assert wrong.status_code == 404
    assert (
        await client.post(
            "/api/slots/block",
            json={"business_id": "r_gb_01", "date": day(2).isoformat()},
            headers=pc(services, "r_gb_01"),
        )
    ).status_code == 400


async def test_doctor_leave_endpoint(client: httpx.AsyncClient, services: Services) -> None:
    body = {"date": day(1).isoformat(), "on_leave": True}
    assert (await client.post("/api/doctors/d_gb_01_derm_1/leave", json=body)).status_code == 403
    r = await client.post("/api/doctors/d_gb_01_derm_1/leave", json=body, headers=pc(services, "h_gb_01"))
    assert r.json()["on_leave_dates"] == [day(1).isoformat()]
    ctx = services.tool_context(phone=CALLER)
    booked = await run_tool(
        ctx,
        "book_appointment",
        {"doctor_id": "d_gb_01_derm_1", "date": day(1).isoformat(), "time": "11:00", "name": "L"},
    )
    assert booked["error"] == "DOCTOR_ON_LEAVE"
    slots = await run_tool(ctx, "get_doctor_slots", {"doctor_id": "d_gb_01_derm_1", "date": day(1).isoformat()})
    assert slots["on_leave"] is True
    r = await client.post(
        "/api/doctors/d_gb_01_derm_1/leave", json={**body, "on_leave": False}, headers=pc(services, "h_gb_01")
    )
    assert r.json()["on_leave_dates"] == []


async def test_payment_webhook(client: httpx.AsyncClient, services: Services) -> None:
    bid, call_id = await call_booking(
        services,
        "book_appointment",
        {"doctor_id": "d_gb_01_derm_1", "date": day(1).isoformat(), "time": "11:00", "name": "Lakshmi"},
    )
    link = await run_tool(
        services.tool_context(call_id=call_id, phone=CALLER), "create_payment_link", {"booking_id": bid}
    )
    raw = json.dumps({"event": "payment.paid", "payment_id": link["payment_id"], "provider_ref": "ref_1"}).encode()

    bad = await client.post("/api/payments/webhook", content=raw, headers={"X-Vaani-Signature": "deadbeef"})
    assert bad.status_code == 401
    unsigned = await client.post("/api/payments/webhook", content=raw)
    assert unsigned.status_code == 401

    ok = await client.post(
        "/api/payments/webhook", content=raw, headers={"X-Vaani-Signature": sign(WEBHOOK_SECRET, raw)}
    )
    assert ok.status_code == 200 and ok.json()["booking_status"] == "paid" and ok.json()["already_paid"] is False
    again = await client.post(
        "/api/payments/webhook", content=raw, headers={"X-Vaani-Signature": sign(WEBHOOK_SECRET, raw)}
    )
    assert again.json()["already_paid"] is True

    booking = (await client.get(f"/api/bookings/{bid}")).json()
    assert booking["status"] == "paid" and booking["payments"][0]["status"] == "paid"
    events = [e["type"] for e in await services.store.events(call_id)]
    assert events.count("payment_updated") == 1


async def test_webhook_needs_secret(client: httpx.AsyncClient, services: Services) -> None:
    services.settings.payment_webhook_secret = ""
    r = await client.post("/api/payments/webhook", content=b"{}", headers={"X-Vaani-Signature": "x"})
    assert r.status_code == 503


async def test_mock_pay(client: httpx.AsyncClient, services: Services) -> None:
    bid, _ = await call_booking(
        services,
        "book_table",
        {"restaurant_id": "r_jh_01", "date": day(3).isoformat(), "time": "20:30", "party_size": 10, "name": "Rohit"},
    )
    r = await client.post(f"/api/payments/{bid}/mock-pay")
    assert r.status_code == 200 and r.json()["booking_status"] == "paid" and r.json()["amount_inr"] == 500
    assert (await client.post(f"/api/payments/{bid}/mock-pay")).status_code == 409
    small, _ = await call_booking(
        services,
        "book_table",
        {"restaurant_id": "r_jh_01", "date": day(1).isoformat(), "time": "20:30", "party_size": 2, "name": "S"},
    )
    assert (await client.post(f"/api/payments/{small}/mock-pay")).json()["detail"]["error"] == "NOTHING_TO_PAY"


async def test_simulate_booking(client: httpx.AsyncClient, services: Services, messenger: MockMessenger) -> None:
    r = await client.post(
        "/api/dev/simulate-booking", json={"business_id": "r_jh_01", "date": day(1).isoformat(), "party_size": 4}
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["booking"]["ok"] and data["confirmation"]["status"] == "sent" and messenger.sent
    types = [e["type"] for e in await services.store.events(data["call_id"])]
    assert types[:3] == ["call_started", "language_detected", "agent_switched"]
    assert "booking_created" in types and types[-1] == "call_ended"

    h = await client.post("/api/dev/simulate-booking", json={"business_id": "h_gb_01", "date": day(1).isoformat()})
    assert h.status_code == 200 and h.json()["booking"]["fee_inr"] > 0

    services.settings.dev_simulate = False
    assert (await client.post("/api/dev/simulate-booking", json={"business_id": "r_jh_01"})).status_code == 404


async def test_webrtc_offer_guards(client: httpx.AsyncClient, services: Services) -> None:
    """No key → 503; over the call cap → 503 BUSY; PATCH without pc_id → 400."""
    from backend.api import voice_routes

    services.settings.sarvam_api_key = ""
    r = await client.post("/webrtc/offer", json={"sdp": "x", "type": "offer"})
    assert r.status_code == 503 and r.json()["detail"]["error"] == "VOICE_NOT_CONFIGURED"
    services.settings.sarvam_api_key = "test-only"
    services.settings.max_web_calls = 0
    r = await client.post("/webrtc/offer", json={"sdp": "x", "type": "offer"})
    assert r.status_code == 503 and r.json()["detail"]["error"] == "BUSY"
    r = await client.patch("/webrtc/offer", json={"candidates": []})
    assert r.status_code == 400
    assert voice_routes._calls == set()
