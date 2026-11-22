"""Text-mode agent: session runner, guards, read-back rule, outcome JSON (scripted LLM, no network)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from backend.api.deps import Services
from backend.clock import today_ist
from backend.flows.nodes import confirm_booking
from backend.flows.session import Session
from backend.voice.llm import LLMReply, ScriptedLLM, parse_reply

pytestmark = pytest.mark.db
CALLER = "+919876543210"


def act(tool: str, say: str = "", **args: Any) -> dict[str, Any]:
    return {"say": say, "actions": [{"tool": tool, "args": args}]}


def speak(text: str) -> dict[str, Any]:
    return {"say": text, "actions": []}


async def new_session(services: Services, script: list[Any]) -> tuple[Session, ScriptedLLM]:
    llm = ScriptedLLM(script)
    s = Session(services, llm, phone=CALLER)
    await s.start()
    return s, llm


async def test_restaurant_booking_end_to_end(reseed: None, services: Services) -> None:
    s, llm = await new_session(
        services,
        [
            act("route_to", "Oka second andi…", service="restaurant"),
            act("search_restaurants", area="Jubilee Hills", date="repu", party_size=2),
            speak("Moodu options unnai andi: Spice Garden, 4.5; Coastal Kitchen, 4.3; Green Leaf, 4.2. Edi kavali?"),
        ],
    )
    t1 = await s.handle("Jubilee Hills lo repu iddaru ki table kavali")
    assert "Spice Garden" in t1.reply and s.ctx.service == "restaurant" and s.ctx.language == "te"
    assert s.ctx.slots["party_size"] == 2  # "iddaru" read in code

    # Everything known from the caller's words → code builds the read-back, no LLM call.
    t2 = await s.handle("Spice Garden, 8:30 ki. Peru Ravi.")
    assert t2.reply.startswith("repu raatri 8:30 ki Spice Garden lo 2 mandi ki, Ravi garu peru meeda")
    assert s.ctx.pending is not None and s.ctx.pending.args["time"] == "20:30"

    t3 = await s.handle("Avunu")
    assert s.ctx.booking_id and s.ctx.booking_id in t3.reply
    assert len(llm.calls) == 3  # only turn 1 used the LLM

    row = await services.store.fetchrow(
        "select * from public.bookings where booking_id = %(b)s", {"b": s.ctx.booking_id}
    )
    assert (
        row
        and row["business_id"] == "r_jh_01"
        and row["party_size"] == 2
        and row["date"] == today_ist() + timedelta(days=1)
    )
    assert row["time"].strftime("%H:%M") == "20:30" and row["language"] == "te" and row["phone"] == CALLER
    assert services.messenger.sent  # type: ignore[attr-defined]

    out = await s.end()
    assert set(out) == {"call_id", "language", "service", "intent", "slots", "outcome", "booking_id", "latency_ms"}
    assert out["outcome"] == "booked" and out["intent"] == "book" and out["language"] == ["te", "en"]
    assert set(out["latency_ms"]) == {"stt", "llm_first_token", "tts_first_audio", "turn_median"}
    call = await services.store.fetchrow(
        "select outcome_json, summary, transcript from public.calls where call_id = %(c)s", {"c": s.ctx.call_id}
    )
    assert call and call["outcome_json"]["booking_id"] == s.ctx.booking_id and "booked" in call["summary"]
    assert [x["speaker"] for x in call["transcript"]][:2] == ["vaani", "caller"]
    types = [e["type"] for e in await services.store.events(s.ctx.call_id or "")]
    for t in (
        "call_started",
        "language_detected",
        "agent_switched",
        "slot_filled",
        "tool_called",
        "transcript",
        "booking_created",
        "call_ended",
    ):
        assert t in types, t


async def test_readback_comes_from_code_not_the_llm(reseed: None, services: Services) -> None:
    """The LLM says '8:30' but passes 19:30: the caller's words win, and the read-back matches the booking."""
    s, _ = await new_session(
        services,
        [
            act("route_to", service="restaurant"),
            act(
                "propose_booking",
                restaurant="Spice Garden",
                date="2026-01-01",
                time="19:30",
                party_size=6,
                name="Pranav",
            ),
        ],
    )
    await s.handle("Spice Garden lo kal 6 logon ke liye, 8:30 baje, naam Pranav")
    assert s.ctx.pending and s.ctx.pending.args["time"] == "20:30"
    assert s.ctx.pending.args["date"] == (today_ist() + timedelta(days=1)).isoformat()


async def test_confirm_needs_an_earlier_readback(reseed: None, services: Services) -> None:
    s, _ = await new_session(services, [])
    s.ctx.turn = 1
    res, _ = await confirm_booking(s, {})
    assert res["error"] == "NO_READBACK"
    from backend.flows.nodes import propose_booking

    s.ctx.service = "restaurant"
    s.ctx.slots["name"] = "Asha"  # names only come from the caller (extracted), never invented
    res, _ = await propose_booking(
        s,
        {
            "restaurant": "r_jh_01",
            "date": (today_ist() + timedelta(days=1)).isoformat(),
            "time": "20:30",
            "party_size": 2,
            "name": "A",
        },
    )
    assert res["ok"] and "force_say" in res
    res, _ = await confirm_booking(s, {})
    assert res["error"] == "WAIT_FOR_YES"  # same turn: the caller hasn't said yes yet
    s.ctx.turn = 2
    res, _ = await confirm_booking(s, {})
    assert res["ok"] and res["booking_id"].startswith("VN-")


async def test_emergency_guard_never_calls_the_llm(reseed: None, services: Services) -> None:
    s, llm = await new_session(services, [])  # any LLM call would fail the test
    t = await s.handle("Naanna ki gunde noppi, chaathi lo baruvuga undi")
    assert t.guard == "emergency" and "108" in t.reply and "112" in t.reply and llm.calls == []
    assert s.ctx.emergency and s.ctx.outcome == "redirected_emergency"
    from backend.flows.nodes import propose_appointment

    res, _ = await propose_appointment(s, {"doctor": "d_gb_01_derm_1", "date": "repu", "time": "11:00", "name": "X"})
    assert res["error"] == "EMERGENCY_CALL"


async def test_unsupported_area_guard(reseed: None, services: Services) -> None:
    s, llm = await new_session(services, [])
    t = await s.handle("Kukatpally lo manchi restaurant cheppandi")
    assert t.guard == "unsupported_area" and "Jubilee Hills" in t.reply and llm.calls == []
    assert s.ctx.unsupported_heard == "Kukatpally" and s.ctx.outcome == "declined_unsupported_area"


async def test_faq_guard_answers_from_data(reseed: None, services: Services) -> None:
    s, llm = await new_session(services, [])
    t = await s.handle("Spice Garden Jubilee Hills lo parking unda?")
    assert t.guard == "faq" and "parking" in t.reply.lower() and llm.calls == []
    assert s.ctx.outcome == "answered_faq"


async def test_otp_is_redacted_and_refused(reseed: None, services: Services) -> None:
    s, llm = await new_session(services, [speak("Sare andi.")])
    t = await s.handle("na OTP 482913, card number 4111 1111 1111 1111")
    assert t.guard == "secret_redacted" and t.reply.startswith(s.phrase("never_ask_otp", s.ctx.turn))
    sent = " ".join(m["content"] for m in llm.calls[0])
    assert "482913" not in sent and "4111" not in sent and "[redacted]" in sent
    # Never stored either: transcript and transcript events hold the redacted text only.
    assert all("482913" not in x["text"] for x in s.ctx.transcript)
    events = await services.store.events(s.ctx.call_id or "")
    assert all("482913" not in str(e["payload"]) for e in events)


async def test_unknown_function_and_bad_json_are_survivable(reseed: None, services: Services) -> None:
    s, llm = await new_session(services, [act("make_coffee"), speak("Cheppandi andi.")])
    t = await s.handle("Hello")
    assert t.reply == "Cheppandi andi." and t.actions[0]["ok"] is False
    tool_msg = next(m["content"] for m in llm.calls[1] if m["content"].startswith("<tool_results>"))
    assert "UNKNOWN_FUNCTION" in tool_msg and "route_to" in tool_msg


def test_parse_reply_is_tolerant() -> None:
    assert parse_reply('```json\n{"say": "hi", "actions": []}\n```').say == "hi"
    r = parse_reply('Sure! {"say": "x", "actions": [{"tool": "end_call", "args": {"reason": "bye"}}]}')
    assert r.actions[0].tool == "end_call" and r.actions[0].args == {"reason": "bye"}
    assert parse_reply("plain words").say == "plain words" and parse_reply("plain words").parse_error
    bad = parse_reply('{"say": "x", "actions": [')
    assert bad.parse_error and bad.say == ""
    assert parse_reply('{"say": "x", "actions": [{"tool": "t", "args": "oops"}]}').actions[0].args == {}


async def test_language_switch_and_hindi_readback(reseed: None, services: Services) -> None:
    s, _ = await new_session(services, [act("route_to", service="restaurant"), speak("Ji, kitne log?")])
    await s.handle("Royal Zafraan mein kal raat 9 baje table chahiye")
    assert s.ctx.language == "hi" and s.ctx.slots["business_id"] == "r_gb_03"
    t = await s.handle("chaar log, naam Imran")
    assert t.reply == "kal raat 9, Royal Zafraan, 4 log, Imran ji ke naam pe. Confirm karoon?"


class _CountingLLM:
    """Returns valid JSON once, then raises: proves guards/shortcuts don't call it."""

    def __init__(self) -> None:
        self.n = 0

    async def complete(self, messages: Any) -> LLMReply:
        self.n += 1
        raise AssertionError("LLM should not be called")


async def test_plain_yes_without_readback_rebuilds_it(reseed: None, services: Services) -> None:
    s = Session(services, _CountingLLM(), phone=CALLER)
    await s.start()
    s.ctx.service, s.ctx.node, s.ctx.turn = "hospital", "hospital", 3
    s.ctx.slots.update(
        doctor_id="d_gb_01_derm_1",
        business_id="h_gb_01",
        date=(today_ist() + timedelta(days=1)).isoformat(),
        time="11:00",
        name="Lakshmi",
    )
    t = await s.handle("Avunu")
    assert "Dr. Ananya Rao" in t.reply and "Confirm" in t.reply and s.ctx.pending is not None


async def test_llm_cannot_invent_the_callers_name(reseed: None, services: Services) -> None:
    s, _ = await new_session(
        services,
        [
            act("route_to", service="restaurant"),
            act(
                "propose_booking",
                restaurant="Royal Zafraan",
                date="kal",
                time="9 baje",
                party_size=4,
                name="Aapka naam",
            ),
            speak("Aapka naam kya hai ji?"),
        ],
    )
    await s.handle("Gachibowli mein kal raat 9 baje Royal Zafraan, chaar log")
    assert s.ctx.pending is None and s.ctx.slots["name"] is None
