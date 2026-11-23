"""VaaniBrain (voice/brain.py): Session ↔ Pipecat frames, without audio or network.

The brain's outgoing frames are captured by replacing push_frame; the LLM is scripted.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pipecat.frames.frames import EndWorkerFrame, Frame, LLMContextFrame, TTSSpeakFrame, TTSUpdateSettingsFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection

from backend.api.deps import Services
from backend.flows.session import Session
from backend.tests.conftest import CALLER
from backend.voice.brain import VaaniBrain
from backend.voice.llm import ScriptedLLM

pytestmark = pytest.mark.db


def make_brain(services: Services, script: list[Any], **kw: Any) -> tuple[VaaniBrain, list[Frame]]:
    session = Session(services, ScriptedLLM(script), phone=CALLER, channel="web", language="te")
    brain = VaaniBrain(session, **kw)
    sent: list[Frame] = []

    async def capture(frame: Frame, direction: FrameDirection = FrameDirection.DOWNSTREAM) -> None:
        sent.append(frame)

    brain.push_frame = capture  # type: ignore[method-assign]
    return brain, sent


def spoken(frames: list[Frame]) -> list[str]:
    return [f.text for f in frames if isinstance(f, TTSSpeakFrame)]


async def test_greeting_is_spoken_with_ai_disclosure(reseed: None, services: Services) -> None:
    brain, sent = make_brain(services, [])
    await brain.greet()
    assert len(spoken(sent)) == 1 and "AI" in spoken(sent)[0]
    assert brain.session.ctx.call_id is not None


async def test_emergency_turn_no_llm_digits_spoken(reseed: None, services: Services) -> None:
    brain, sent = make_brain(services, [])  # any LLM call would fail
    await brain.greet()
    await brain._handle_turn("I can't breathe, my father has chest pain", 1)
    reply = spoken(sent)[-1]
    assert brain.session.ctx.emergency
    assert "one one two" in reply and "one zero eight" in reply  # helplines read digit by digit
    assert not any(ch.isdigit() for ch in reply)


async def test_language_switch_updates_tts(reseed: None, services: Services) -> None:
    brain, sent = make_brain(services, [])
    await brain.greet()
    await brain._handle_turn("Mujhe Kondapur mein restaurant chahiye", 1)  # Hindi + unsupported area guard
    assert any(isinstance(f, TTSUpdateSettingsFrame) for f in sent)
    assert brain.session.ctx.language == "hi"


async def test_slow_turn_speaks_a_filler_first(reseed: None, services: Services) -> None:
    class SlowLLM(ScriptedLLM):
        async def complete(self, messages: Any) -> Any:
            await asyncio.sleep(0.3)
            return await super().complete(messages)

    session = Session(services, SlowLLM([{"say": "Ae area lo kavali andi?", "actions": []}]), phone=CALLER)
    brain = VaaniBrain(session, filler_after_s=0.05)
    sent: list[Frame] = []

    async def capture(frame: Frame, direction: FrameDirection = FrameDirection.DOWNSTREAM) -> None:
        sent.append(frame)

    brain.push_frame = capture  # type: ignore[method-assign]
    await brain.greet()
    await brain._handle_turn("restaurant kavali", 1)
    lines = spoken(sent)
    fillers = {p for x in services.catalog.agent_phrases if x.key == "filler_checking" for p in x.te_en}
    assert len(lines) == 3 and lines[1] in fillers  # greeting, filler while the LLM thinks, reply
    assert lines[2] == "Ae area lo kavali andi?"


async def test_stale_reply_is_skipped(reseed: None, services: Services) -> None:
    brain, sent = make_brain(services, [{"say": "Ae area andi?", "actions": []}])
    await brain.greet()
    brain._latest_seq = 2  # the caller already started another turn
    before = len(spoken(sent))
    await brain._handle_turn("restaurant kavali", 1)
    assert len(spoken(sent)) == before  # nothing said for the superseded turn


async def test_silence_checks_then_goodbye(reseed: None, services: Services) -> None:
    brain, sent = make_brain(services, [], max_silence_checks=2)
    await brain.greet()
    for _ in range(3):
        await brain.on_user_idle()
    lines = spoken(sent)
    assert len(lines) == 4  # greeting + 2 checks + goodbye
    assert brain.session.ctx.ended and any(isinstance(f, EndWorkerFrame) for f in sent)


def test_last_user_text_from_context() -> None:
    ctx = LLMContext()
    ctx.add_message({"role": "user", "content": "Kal raat 6 log"})
    assert VaaniBrain._last_user_text(LLMContextFrame(context=ctx)) == "Kal raat 6 log"


async def test_latency_row_recorded_at_first_tts_audio(reseed: None, services: Services) -> None:
    import time

    brain, _ = make_brain(services, [])
    await brain.greet()
    brain._t_user_stop = time.perf_counter() - 0.3
    brain._t_text = time.perf_counter()
    brain._awaiting_audio = True
    await brain._handle_turn("Kondapur lo restaurant kavali", 1)  # guard reply, no LLM
    await brain.on_tts_audio()
    await brain.on_tts_audio()  # later frames of the same turn don't add rows
    rows = brain.session.ctx.voice_turns
    assert len(rows) == 1 and set(rows[0]) == {"turn", "stt", "llm_first_token", "tts_first_audio", "turn_total"}
    assert rows[0]["stt"] >= 300 and rows[0]["turn_total"] >= rows[0]["stt"]


async def test_very_slow_llm_gets_a_second_filler_and_a_failed_one_an_apology(
    reseed: None, services: Services
) -> None:
    class StallingLLM(ScriptedLLM):
        async def complete(self, messages: Any) -> Any:
            await asyncio.sleep(0.4)
            raise TimeoutError("provider stalled")

    session = Session(services, StallingLLM([]), phone=CALLER)
    brain = VaaniBrain(session, filler_after_s=0.05, still_checking_after_s=0.1)
    sent: list[Frame] = []

    async def capture(frame: Frame, direction: FrameDirection = FrameDirection.DOWNSTREAM) -> None:
        sent.append(frame)

    brain.push_frame = capture  # type: ignore[method-assign]
    await brain.greet()
    await brain._handle_turn("restaurant kavali", 1)
    lines = spoken(sent)
    # greeting, filler at 0.05 s, "still checking" at 0.15 s, then an apology instead of silence
    assert len(lines) == 4 and lines[-1] == session.phrase("didnt_catch_that")
