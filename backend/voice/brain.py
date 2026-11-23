"""VaaniBrain: the Pipecat processor that puts the Phase 3 Session where an LLM service would go.

    transport.input → STT → user aggregator (VAD, turn end, barge-in, idle) → VaaniBrain → TTS → transport.output

The user aggregator ends a turn and pushes an `LLMContextFrame`; the brain takes the caller's
final words from it, runs `Session.handle` (redaction, guards, extraction, read-backs, the
JSON-action LLM loop: every rule stays in code), and pushes `TTSSpeakFrame`s with the reply
spelled out by the normaliser. While it thinks it can speak a short filler, so the caller
hears something within about a second. It also measures latency per turn and barge-in time.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    EndWorkerFrame,
    Frame,
    InterruptionFrame,
    LLMContextFrame,
    StartFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.aggregators.llm_context import standard_message_text
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from backend.flows.session import Session
from backend.voice.normalizer import normalize
from backend.voice.tts import language_update


def _ms(a: float | None, b: float | None) -> int | None:
    return None if a is None or b is None else max(0, round((b - a) * 1000))


class VaaniBrain(FrameProcessor):
    def __init__(
        self,
        session: Session,
        *,
        filler_after_s: float = 0.6,
        max_silence_checks: int = 2,
        on_call_end: Callable[[], Awaitable[None]] | None = None,
        still_checking_after_s: float = 3.5,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.session = session
        self.filler_after_s = filler_after_s
        self.still_checking_after_s = still_checking_after_s
        self.max_silence_checks = max_silence_checks
        self.on_call_end = on_call_end
        self._lock = asyncio.Lock()
        self._tts_lang = session.ctx.language
        self._turn_tasks: set[asyncio.Task[None]] = set()
        self._silence_checks = 0
        self._ending = False
        # Per-turn timing (perf_counter seconds)
        self._t_user_stop: float | None = None
        self._t_text: float | None = None
        self._t_first_speak: float | None = None
        self._turn_no = 0
        self._latest_seq = 0  # caller turns received; a reply older than the newest is stale
        self._awaiting_audio = False
        # Barge-in timing
        self._bot_speaking = False
        self._t_barge: float | None = None

    # -- frames ------------------------------------------------------------------

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, LLMContextFrame):
            # End of a caller turn. Don't pass it on: there is no LLM service downstream.
            text = self._last_user_text(frame)
            if text:
                self._t_text = time.perf_counter()
                self._t_first_speak = None
                self._awaiting_audio = True  # the turn's first audio (filler or reply) is "time to first audio"
                self._silence_checks = 0
                self._latest_seq += 1
                task = self.create_task(self._handle_turn(text, self._latest_seq), name="vaani-turn")
                self._turn_tasks.add(task)
                task.add_done_callback(self._turn_tasks.discard)
            return
        if isinstance(frame, UserStartedSpeakingFrame):
            if self._bot_speaking and self._t_barge is None:
                self._t_barge = time.perf_counter()
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            # The VAD confirms the stop `stop_secs` after the caller's last sound.
            self._t_user_stop = time.perf_counter() - frame.stop_secs
        elif isinstance(frame, InterruptionFrame) and self._bot_speaking and self._t_barge is None:
            self._t_barge = time.perf_counter()
        elif isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            if self._t_barge is not None:
                ms = _ms(self._t_barge, time.perf_counter()) or 0
                self.session.ctx.barge_in_ms.append(ms)
                summary = f"Caller interrupted → Vaani stopped in {ms} ms"
                await self.session.emit("tool_called", {"tool": "barge_in", "summary": summary, "ms": ms, "ok": True})
                self._t_barge = None
        await self.push_frame(frame, direction)

    async def cleanup(self) -> None:
        """Call over: stop any turn still waiting on the LLM (it would only speak to nobody)."""
        for task in list(self._turn_tasks):
            await self.cancel_task(task)
        await super().cleanup()  # type: ignore[no-untyped-call]

    @staticmethod
    def _last_user_text(frame: LLMContextFrame) -> str:
        for message in reversed(frame.context.messages):
            if isinstance(message, dict) and message.get("role") == "user":
                return standard_message_text(message).strip()
        return ""

    # -- speaking ----------------------------------------------------------------

    async def say(self, text: str) -> None:
        """Speak `text` in the call's language (switching the TTS voice language if it changed)."""
        text = text.strip()
        if not text:
            return
        lang = self.session.ctx.language
        if lang != self._tts_lang:
            await self.push_frame(language_update(self.session.settings, lang))
            self._tts_lang = lang
        if self._t_first_speak is None and self._t_text is not None:
            self._t_first_speak = time.perf_counter()
        await self.push_frame(TTSSpeakFrame(text=normalize(text, lang), append_to_context=False))

    async def greet(self) -> None:
        greeting = await self.session.start()
        await self.say(greeting)

    async def _handle_turn(self, text: str, seq: int) -> None:
        async with self._lock:
            if self._ending:
                return
            self._turn_no += 1
            spoke_filler = False

            async def progress(line: str) -> None:
                nonlocal spoke_filler
                if not spoke_filler:  # one filler per turn is plenty
                    spoke_filler = True
                    await self.say(line)

            async def filler_after_delay() -> None:
                await asyncio.sleep(self.filler_after_s)
                await progress(self.session.phrase("filler_checking"))
                # Still waiting (a slow LLM step): one more short line so the caller isn't left in silence.
                await asyncio.sleep(self.still_checking_after_s)
                await self.say(self.session.phrase("filler_checking", self._turn_no + 1))

            self.session.on_progress = progress
            booking_before = self.session.ctx.booking_id
            timer = asyncio.create_task(filler_after_delay())
            try:
                result = await self.session.handle(text)
            except Exception:
                logger.exception("Session.handle failed")
                timer.cancel()
                await self.say(self.session.phrase("didnt_catch_that"))
                return
            finally:
                timer.cancel()
                self.session.on_progress = None
            booked_now = self.session.ctx.booking_id is not None and booking_before is None
            stale = seq < self._latest_seq
            # The caller kept talking ("7 baje theek hai. … Mera naam Pranav hai."): the next turn
            # answers both, so skip this reply, unless it's an emergency line or a booking confirmation.
            if stale and result.guard != "emergency" and not booked_now and not self.session.ctx.ended:
                logger.info(f"skipping stale reply for turn {seq}: {result.reply!r}")
                return  # the newer turn's timing (already started) measures its own first audio
            await self.say(result.reply)
            if self.session.ctx.ended:
                await self.end_call()

    async def on_user_idle(self) -> None:
        """Caller silent: "Hello, vinipistunda?" up to twice, then a polite goodbye."""
        if self._ending or self._lock.locked():
            return
        self._silence_checks += 1
        if self._silence_checks <= self.max_silence_checks:
            await self.say(self.session.phrase("silence_check"))
            return
        summary = "No answer after 2 checks → ended the call politely"
        await self.session.emit("tool_called", {"tool": "end_call", "summary": summary, "ms": 0, "ok": True})
        await self.say(self.session.phrase("goodbye"))
        self.session.ctx.ended = True
        await self.end_call()

    async def end_call(self) -> None:
        """Let the last line play, then close the pipeline (EndWorkerFrame flushes queued frames)."""
        if self._ending:
            return
        self._ending = True
        await self.push_frame(EndWorkerFrame())
        if self.on_call_end is not None:
            await self.on_call_end()

    # -- latency -----------------------------------------------------------------

    async def on_tts_audio(self) -> None:
        """Called by AudioTap for every TTS audio frame; the first one after a turn is "first audio".

        (BotStartedSpeakingFrame isn't enough: it doesn't fire again while audio runs on from one
        line into the next, which once logged a 15 s "TTS" time.)"""
        if self._awaiting_audio and self._t_first_speak is not None:
            self._awaiting_audio = False
            await self._record_latency(time.perf_counter())

    async def _record_latency(self, t_audio: float) -> None:
        row = {
            "turn": self._turn_no,
            # end of the caller's speech → final transcript + end-of-turn decision
            "stt": _ms(self._t_user_stop, self._t_text),
            # transcript → first words handed to the TTS (guards, LLM, filler)
            "llm_first_token": _ms(self._t_text, self._t_first_speak),
            # first words → first audio frame leaving the transport
            "tts_first_audio": _ms(self._t_first_speak, t_audio),
            # end of the caller's speech → Vaani audible
            "turn_total": _ms(self._t_user_stop, t_audio),
        }
        clean = {k: v for k, v in row.items() if v is not None}
        self.session.ctx.voice_turns.append(clean)
        await self.session.emit("latency", clean)
        self._t_user_stop = self._t_text = self._t_first_speak = None


class AudioTap(FrameProcessor):
    """Sits between the TTS and the output transport; tells the brain when TTS audio flows."""

    def __init__(self, brain: VaaniBrain, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.brain = brain

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame) and direction == FrameDirection.DOWNSTREAM:
            await self.brain.on_tts_audio()
        await self.push_frame(frame, direction)
