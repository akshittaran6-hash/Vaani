"""One Pipecat pipeline per call (browser WebRTC now, Twilio Media Streams in Phase 6).

    transport.input → STT (Sarvam) → user aggregator (Silero VAD + Smart Turn, barge-in,
    silence) → VaaniBrain (Phase 3 Session) → TTS (Sarvam Bulbul) → transport.output

`run_call()` takes any Pipecat transport, so Phase 6 only swaps the transport.
Checked against pipecat-ai 1.16 (PipelineWorker / WorkerRunner, LLMContextAggregatorPair).
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.transports.base_transport import BaseTransport
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner

from backend.api.deps import Services
from backend.flows.session import Session
from backend.voice import events
from backend.voice.brain import AudioTap, VaaniBrain
from backend.voice.llm import LLM
from backend.voice.stt import make_stt
from backend.voice.tts import SAMPLE_RATE, make_tts

DEFAULT_LANGUAGE = "te"  # greeting language until the caller's first words decide


async def run_call(
    transport: BaseTransport,
    svc: Services,
    llm: LLM,
    *,
    phone: str,
    channel: str = "web",
    event_key: str | None = None,
) -> Session:
    """Run one call to the end. Returns the finished Session (calls row already written)."""
    settings = svc.settings
    session = Session(svc, llm, phone=phone, channel=channel, language=DEFAULT_LANGUAGE)
    if event_key:

        async def forward(type_: str, payload: dict[str, Any]) -> None:
            await events.publish(event_key, type_, payload)

        session.listeners.append(forward)

    stt = make_stt(settings)
    tts = make_tts(settings, DEFAULT_LANGUAGE)
    context = LLMContext()
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
            # Smart Turn v3 decides end of turn; when it thinks the caller isn't finished it waits up
            # to stop_secs of silence (3 s by default). It is less sure on Telugu/Hindi, so cap it.
            user_turn_strategies=UserTurnStrategies(
                stop=[
                    TurnAnalyzerUserTurnStopStrategy(
                        turn_analyzer=LocalSmartTurnAnalyzerV3(
                            params=SmartTurnParams(stop_secs=settings.turn_max_silence_s)
                        )
                    )
                ]
            ),
            user_idle_timeout=settings.silence_timeout_s,
        ),
    )
    user_aggregator = aggregators.user()
    brain = VaaniBrain(session, filler_after_s=settings.filler_after_s)

    pipeline = Pipeline([transport.input(), stt, user_aggregator, brain, tts, AudioTap(brain), transport.output()])
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=SAMPLE_RATE,
            enable_metrics=True,
        ),
        enable_rtvi=False,
        idle_timeout_secs=None,  # the brain's silence handler ends quiet calls
    )
    runner = WorkerRunner(handle_sigint=False)
    finished = False

    async def finish() -> None:
        nonlocal finished
        if finished:
            return
        finished = True
        try:
            await session.end()  # post-call: transcript, outcome JSON, tool timeline, latency → calls row
        except Exception:
            logger.exception("post-call write failed")

    async def on_idle(_aggregator: Any) -> None:
        await brain.on_user_idle()

    async def on_connected(_transport: Any, _client: Any) -> None:
        await brain.greet()

    async def on_disconnected(_transport: Any, _client: Any) -> None:
        await finish()
        await worker.cancel()

    user_aggregator.add_event_handler("on_user_turn_idle", on_idle)
    transport.add_event_handler("on_client_connected", on_connected)
    transport.add_event_handler("on_client_disconnected", on_disconnected)

    try:
        await runner.run(worker)
    finally:
        await finish()
        if event_key:
            await events.publish(event_key, "call_closed", {})
    return session
