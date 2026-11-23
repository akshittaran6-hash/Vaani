"""Browser voice calls (Phase 4): POST /webrtc/offer, PATCH /webrtc/offer, /voice-test, /voice/events.

One SmallWebRTC peer connection = one call = one pipeline (backend/voice/pipeline.py).
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger

from backend.api.deps import Svc, fail
from backend.voice import events

router = APIRouter()
STATIC = Path(__file__).resolve().parents[1] / "static"
E164 = re.compile(r"^\+\d{10,15}$")
_calls: set[asyncio.Task[Any]] = set()  # keep references so running calls aren't garbage-collected
_handler: Any = None


def _request_handler() -> Any:
    global _handler
    if _handler is None:
        from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequestHandler

        _handler = SmallWebRTCRequestHandler()
    return _handler


@router.post("/webrtc/offer")
async def webrtc_offer(body: dict[str, Any], request: Request, svc: Svc) -> dict[str, Any]:
    """SDP offer in → SDP answer out; the call's pipeline starts in the background."""
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequest
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

    from backend.voice.pipeline import run_call

    if not svc.settings.sarvam_api_key:
        fail("VOICE_NOT_CONFIGURED", "SARVAM_API_KEY is not set", 503)
    llm = getattr(request.app.state, "llm", None)
    if llm is None:
        from backend.voice.llm import from_env

        llm = request.app.state.llm = from_env(
            timeout_s=svc.settings.llm_voice_timeout_s, retries=svc.settings.llm_voice_retries
        )
    try:
        offer = SmallWebRTCRequest.from_dict(dict(body))
    except TypeError as e:
        fail("INVALID_ARGS", f"Expected an SDP offer: {e}")
    data = offer.request_data if isinstance(offer.request_data, dict) else {}
    # Browser calls have no caller ID: the page may pass a number for the WhatsApp card.
    phone = str(data.get("phone") or "")
    phone = phone if E164.match(phone) else svc.settings.web_caller_phone

    async def on_connection(connection: Any) -> None:
        transport = SmallWebRTCTransport(
            webrtc_connection=connection,
            params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
        )
        task = asyncio.create_task(
            run_call(transport, svc, llm, phone=phone, channel="web", event_key=connection.pc_id)
        )
        _calls.add(task)
        task.add_done_callback(_calls.discard)
        task.add_done_callback(lambda t: t.exception() and logger.error(f"call failed: {t.exception()!r}"))

    answer: dict[str, Any] = await _request_handler().handle_web_request(
        request=offer, webrtc_connection_callback=on_connection
    )
    return answer


@router.patch("/webrtc/offer")
async def webrtc_ice(body: dict[str, Any]) -> dict[str, bool]:
    """Trickle ICE candidates (the Pipecat JS client sends these)."""
    from pipecat.transports.smallwebrtc.request_handler import IceCandidate, SmallWebRTCPatchRequest

    candidates = [
        IceCandidate(
            candidate=c.get("candidate", ""), sdp_mid=c.get("sdp_mid"), sdp_mline_index=c.get("sdp_mline_index")
        )
        for c in body.get("candidates", [])
    ]
    await _request_handler().handle_patch_request(SmallWebRTCPatchRequest(pc_id=body["pc_id"], candidates=candidates))
    return {"ok": True}


@router.get("/voice/events/{pc_id}")
async def voice_events(pc_id: str) -> StreamingResponse:
    """Live transcript / latency / tool events for one browser call (Server-Sent Events)."""

    async def stream() -> AsyncIterator[str]:
        q = events.subscribe(pc_id)
        try:
            yield ": connected\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(item, ensure_ascii=False, default=str)}\n\n"
                if item["type"] == "call_closed":
                    return
        finally:
            events.unsubscribe(pc_id, q)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/voice-test", include_in_schema=False)
async def voice_test() -> FileResponse:
    return FileResponse(STATIC / "voice_test.html", media_type="text/html")
