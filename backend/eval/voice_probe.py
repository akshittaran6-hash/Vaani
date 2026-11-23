"""Headless voice test: a WebRTC "caller" talks to a running Vaani server and measures it.

    uv run python -m backend.eval.voice_probe                      # both demo scenarios
    uv run python -m backend.eval.voice_probe --scenario hindi_restaurant --barge-in

The caller's lines are synthesised once with Sarvam TTS (a different voice from Vaani's) and
cached in backend/eval/recordings/. The probe streams them over WebRTC (aiortc), waits for
Vaani to finish each reply, and records, from the caller's side:
- time to first audio: end of the caller's line → Vaani audible (includes network + jitter buffer)
- barge-in: caller starts talking over Vaani → Vaani's audio stops
It also listens to /voice/events for the transcript and the server-side latency rows, and
prints a summary + writes JSON to backend/eval/results/voice-<stamp>.json.

Needs the server running (e.g. `VAANI_DEV_DB=ephemeral uv run uvicorn backend.api.app:app`).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import fractions
import io
import json
import statistics
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import numpy as np
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from av import AudioFrame

from backend.clock import IST
from backend.config import get_settings

RATE = 48000
FRAME = 960  # 20 ms at 48 kHz
RECORDINGS = Path(__file__).resolve().parent / "recordings"
RESULTS = Path(__file__).resolve().parent / "results"

SCENARIOS: dict[str, tuple[str, list[str]]] = {
    # DEMO.md: Dumgalli tomorrow for 6 → 8:30 full → 7:00
    "hindi_restaurant": (
        "hi-IN",
        [
            "Jubilee Hills mein kal raat chhah logon ke liye koi achha restaurant batao.",
            "Dumgalli Courtyard, saadhe aath baje.",
            "Saat baje theek hai. Mera naam Pranav hai.",
            "Haan, confirm kar dijiye.",
        ],
    ),
    # DEMO.md / T23: Vaana Grove, Dr. Navisha full → Dr. Suvin at 15:00
    "telugu_hospital": (
        "te-IN",
        [
            "Gachibowli lo repu skin doctor kavali andi.",
            "Vaana Grove lo Dr. Suvin Rellimudi garu tho madhyaanam moodu gantalaki.",
            "Naa peru Lakshmi.",
            "Avunu, confirm cheyandi.",
        ],
    ),
}


# ---------------------------------------------------------------------------
# Audio in / out
# ---------------------------------------------------------------------------


def synth(text: str, lang: str) -> np.ndarray:
    """Caller audio as int16 mono at 48 kHz (cached)."""
    RECORDINGS.mkdir(exist_ok=True)
    key = RECORDINGS / f"caller_{abs(hash((text, lang))) % 10**10}.wav"
    if not key.exists():
        from sarvamai import SarvamAI

        client = SarvamAI(api_subscription_key=get_settings().sarvam_api_key)
        r = client.text_to_speech.convert(
            text=text,
            target_language_code=lang,
            speaker="rahul",
            model="bulbul:v3",
            speech_sample_rate=RATE,
            output_audio_codec="wav",
        )
        key.write_bytes(base64.b64decode("".join(r.audios)))
    with wave.open(io.BytesIO(key.read_bytes())) as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        if w.getframerate() != RATE:
            x = np.linspace(0, len(pcm) - 1, int(len(pcm) * RATE / w.getframerate()))
            pcm = np.interp(x, np.arange(len(pcm)), pcm).astype(np.int16)
    return pcm


class CallerTrack(MediaStreamTrack):
    """Microphone stand-in: silence, or the queued caller line, paced in real time."""

    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._queue = np.zeros(0, dtype=np.int16)
        self._pts = 0
        self._start: float | None = None
        self.speaking_until = 0.0
        self.started_at = 0.0

    def speak(self, pcm: np.ndarray) -> None:
        self._queue = np.concatenate([self._queue, pcm])
        self.started_at = time.perf_counter()
        self.speaking_until = self.started_at + len(pcm) / RATE

    async def recv(self) -> AudioFrame:
        if self._start is None:
            self._start = time.perf_counter()
        wait = self._start + self._pts / RATE - time.perf_counter()
        if wait > 0:
            await asyncio.sleep(wait)
        chunk, self._queue = self._queue[:FRAME], self._queue[FRAME:]
        if len(chunk) < FRAME:
            chunk = np.concatenate([chunk, np.zeros(FRAME - len(chunk), dtype=np.int16)])
        frame = AudioFrame.from_ndarray(chunk.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = RATE
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, RATE)
        self._pts += FRAME
        return frame


@dataclass
class BotEar:
    """Watches Vaani's audio: onsets / offsets of speech by short-term energy."""

    threshold: float = 300.0
    speaking: bool = False
    last_voice: float = 0.0
    onsets: list[float] = field(default_factory=list)
    offsets: list[float] = field(default_factory=list)

    async def listen(self, track: MediaStreamTrack) -> None:
        while True:
            try:
                frame = await track.recv()
            except Exception:  # noqa: BLE001 - track ended
                return
            if not isinstance(frame, AudioFrame):
                continue
            pcm = frame.to_ndarray().astype(np.float32)
            rms = float(np.sqrt(np.mean(pcm**2))) if pcm.size else 0.0
            now = time.perf_counter()
            if rms > self.threshold:
                self.last_voice = now
                if not self.speaking:
                    self.speaking = True
                    self.onsets.append(now)
            elif self.speaking and now - self.last_voice > 0.25:
                self.speaking = False
                self.offsets.append(self.last_voice)

    async def wait_quiet(self, quiet_s: float = 1.6, timeout: float = 30) -> None:
        """Wait until Vaani has spoken and then been quiet for `quiet_s`."""
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            if not self.speaking and self.onsets and time.perf_counter() - self.last_voice > quiet_s:
                return
            await asyncio.sleep(0.05)

    async def wait_onset_after(self, t: float, timeout: float = 15) -> float | None:
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            later = [o for o in self.onsets if o > t]
            if later:
                return later[0]
            await asyncio.sleep(0.01)
        return None


# ---------------------------------------------------------------------------
# One call
# ---------------------------------------------------------------------------


async def run_scenario(base: str, name: str, barge_in: bool) -> dict[str, Any]:
    lang, lines = SCENARIOS[name]
    audio = [synth(t, lang) for t in lines]
    pc = RTCPeerConnection()
    mic = CallerTrack()
    pc.addTrack(mic)
    ear = BotEar()
    listeners: list[asyncio.Task[None]] = []

    @pc.on("track")
    def on_track(track: MediaStreamTrack) -> None:
        if track.kind == "audio":
            listeners.append(asyncio.ensure_future(ear.listen(track)))

    await pc.setLocalDescription(await pc.createOffer())
    async with httpx.AsyncClient(base_url=base, timeout=30) as http:
        r = await http.post("/webrtc/offer", json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})
        r.raise_for_status()
        answer = r.json()
        server_events: list[dict[str, Any]] = []

        async def collect() -> None:
            # pc_id contains "#", so it must be URL-encoded
            async with http.stream("GET", f"/voice/events/{quote(answer['pc_id'], safe='')}", timeout=None) as s:
                async for line in s.aiter_lines():
                    if line.startswith("data: "):
                        server_events.append(json.loads(line[6:]))

        sse = asyncio.ensure_future(collect())
        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))

        turns: list[dict[str, Any]] = []
        barge: dict[str, Any] | None = None
        t0 = time.perf_counter()
        greeting_onset = await ear.wait_onset_after(t0, timeout=20)
        await ear.wait_quiet()
        for i, (text, pcm) in enumerate(zip(lines, audio, strict=True)):
            mic.speak(pcm)
            t_end = mic.speaking_until
            await asyncio.sleep(max(0.0, t_end - time.perf_counter()))
            onset = await ear.wait_onset_after(t_end, timeout=20)
            turns.append(
                {"turn": i + 1, "caller": text, "first_audio_ms": round((onset - t_end) * 1000) if onset else None}
            )
            if barge_in and i == 0 and onset:
                # Talk over Vaani's top-3 answer one second in, with the next line.
                await asyncio.sleep(1.0)
                t_barge = time.perf_counter()
                mic.speak(audio[1])
                offsets_after = None
                end = time.perf_counter() + 5
                while time.perf_counter() < end:
                    offs = [o for o in ear.offsets if o > t_barge]
                    if offs:
                        offsets_after = offs[0]
                        break
                    await asyncio.sleep(0.01)
                barge = {"stop_ms": round((offsets_after - t_barge) * 1000) if offsets_after else None}
                await asyncio.sleep(max(0.0, mic.speaking_until - time.perf_counter()))
                await ear.wait_quiet()
                break  # the barge-in run only checks interruption
            await ear.wait_quiet()
        await asyncio.sleep(1.0)
        await pc.close()
        await asyncio.sleep(1.5)
        sse.cancel()
        for t in listeners:
            t.cancel()

    transcript = [e["payload"] for e in server_events if e["type"] == "transcript"]
    latency = [e["payload"] for e in server_events if e["type"] == "latency"]
    bookings = [e["payload"] for e in server_events if e["type"] == "booking_created"]
    return {
        "scenario": name,
        "greeting_ms": round((greeting_onset - t0) * 1000) if greeting_onset else None,
        "turns": turns,
        "barge_in": barge,
        "server_latency": latency,
        "transcript": transcript,
        "booking": bookings[0] if bookings else None,
        "tools": [e["payload"].get("summary") for e in server_events if e["type"] == "tool_called"],
    }


def _med(xs: list[int | None]) -> int | None:
    vals = [x for x in xs if x is not None]
    return round(statistics.median(vals)) if vals else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--scenario", choices=sorted(SCENARIOS), action="append")
    ap.add_argument("--barge-in", action="store_true", help="talk over Vaani's first answer and time the stop")
    args = ap.parse_args()
    results = [asyncio.run(run_scenario(args.base, s, args.barge_in)) for s in (args.scenario or list(SCENARIOS))]
    for r in results:
        print(f"\n=== {r['scenario']} · greeting after {r['greeting_ms']} ms")
        for line in r["transcript"]:
            print(f"  {line['speaker']:6} [{line['lang']}] {line['text']}")
        print("  client first-audio per turn (ms):", [t["first_audio_ms"] for t in r["turns"]])
        if r["barge_in"]:
            print("  barge-in: Vaani stopped after", r["barge_in"]["stop_ms"], "ms")
        for row in r["server_latency"]:
            print("  server", row)
        print("  booking:", r["booking"])
    all_client = [t["first_audio_ms"] for r in results for t in r["turns"]]
    print(
        "\nclient first audio: median",
        _med(all_client),
        "ms · slowest",
        max((x for x in all_client if x), default=None),
    )
    RESULTS.mkdir(exist_ok=True)
    from datetime import datetime

    out = RESULTS / f"voice-{datetime.now(IST):%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
