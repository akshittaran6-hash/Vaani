"""Text-to-speech provider, chosen by TTS_PROVIDER (Sarvam Bulbul by default).

One Indian voice for te / hi / en-IN; the language follows the caller (set at start, switched
with `language_update()` when the call's language changes). Text reaching the TTS has already
been spelled out by voice/normalizer.py. Checked against pipecat-ai 1.16 (services/sarvam/tts.py).
"""

from __future__ import annotations

from pipecat.frames.frames import TTSUpdateSettingsFrame
from pipecat.services.tts_service import TTSService
from pipecat.transcriptions.language import Language

from backend.config import Settings

LANGUAGES = {"te": Language.TE_IN, "hi": Language.HI_IN, "en": Language.EN_IN}
SAMPLE_RATE = 24000


def make_tts(settings: Settings, lang: str) -> TTSService:
    if settings.tts_provider == "sarvam":
        if not settings.sarvam_api_key:
            raise RuntimeError("SARVAM_API_KEY is not set (see .env.example)")
        from pipecat.services.sarvam.tts import SarvamTTSService

        return SarvamTTSService(
            api_key=settings.sarvam_api_key,
            sample_rate=SAMPLE_RATE,
            settings=SarvamTTSService.Settings(
                model=settings.tts_model,
                voice=settings.tts_voice,
                language=LANGUAGES.get(lang, Language.EN_IN),
            ),
        )
    raise ValueError(f"Unknown TTS_PROVIDER {settings.tts_provider!r}")


def language_update(settings: Settings, lang: str) -> TTSUpdateSettingsFrame:
    """Frame that switches the TTS to the caller's language mid-call."""
    from pipecat.services.sarvam.tts import SarvamTTSService

    return TTSUpdateSettingsFrame(delta=SarvamTTSService.Settings(language=LANGUAGES.get(lang, Language.EN_IN)))
