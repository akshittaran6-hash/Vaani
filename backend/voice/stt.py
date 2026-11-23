"""Speech-to-text provider, chosen by STT_PROVIDER (Sarvam by default).

Sarvam's streaming STT (saaras) auto-detects te / hi / en and, in "translit" mode, returns
romanised text ("Kal shaam saat baje …"): the same form as the test calls the Phase 3
parsers and eval were built on. Checked against pipecat-ai 1.16 (services/sarvam/stt.py).
"""

from __future__ import annotations

from pipecat.services.stt_service import STTService

from backend.config import Settings


def make_stt(settings: Settings) -> STTService:
    if settings.stt_provider == "sarvam":
        if not settings.sarvam_api_key:
            raise RuntimeError("SARVAM_API_KEY is not set (see .env.example)")
        from pipecat.services.sarvam.stt import SarvamSTTService

        return SarvamSTTService(
            api_key=settings.sarvam_api_key,
            model=settings.stt_model,
            mode=settings.stt_mode,
            sample_rate=16000,
        )
    raise ValueError(f"Unknown STT_PROVIDER {settings.stt_provider!r}")
