"""Backend settings from environment / .env (names: docs/CONTRACTS.md §6)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    supabase_db_url: str = ""
    public_base_url: str = "http://localhost:3000"
    demo_area_1: str = "jubilee_hills"
    demo_area_2: str = "gachibowli"
    dev_simulate: bool = False

    payment_provider: Literal["mock", "razorpay", "stripe"] = "mock"
    payment_key_id: str = ""
    payment_key_secret: str = ""
    payment_webhook_secret: str = ""

    # Per-business partner portal passcodes are derived from this (scripts/partner_passcodes.py).
    partner_passcode_secret: str = "vaani-demo"

    @field_validator("partner_passcode_secret")
    @classmethod
    def _default_when_blank(cls, v: str) -> str:
        return v or "vaani-demo"  # `PARTNER_PASSCODE_SECRET=` in .env means "use the demo default"

    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""

    # Voice (Phase 4). Providers are swappable; Sarvam by default (STT saaras, TTS Bulbul).
    sarvam_api_key: str = ""
    stt_provider: Literal["sarvam"] = "sarvam"
    stt_model: str = "saaras:v3"
    # "translit" returns romanised te/hi, which is what the parsers and the eval use.
    stt_mode: Literal["transcribe", "translit", "codemix"] = "translit"
    tts_provider: Literal["sarvam"] = "sarvam"
    tts_model: str = "bulbul:v3"
    tts_voice: str = "priya"  # one voice across te / hi / en-IN (Bulbul voices are Indian)
    tts_api_key: str = ""
    # Seconds of caller silence before "Hello, vinipistunda?" (twice, then goodbye).
    silence_timeout_s: float = 5.0
    # Voice LLM step: give up after this long and retry once (then an apology, never 20 s of silence).
    llm_voice_timeout_s: float = 4.5
    llm_voice_retries: int = 1
    # Longest silence before a turn ends when Smart Turn thinks the caller isn't done.
    turn_max_silence_s: float = 1.5
    # Speak a short filler if the reply isn't ready after this long.
    filler_after_s: float = 0.6
    # Local voice testing without Supabase: VAANI_DEV_DB=ephemeral starts a throwaway Postgres.
    vaani_dev_db: Literal["", "ephemeral"] = ""
    web_caller_phone: str = "+910000000000"

    @field_validator("stt_provider", "tts_provider", mode="before")
    @classmethod
    def _default_provider(cls, v: str) -> str:
        return v or "sarvam"

    @field_validator("stt_mode", mode="before")
    @classmethod
    def _default_mode(cls, v: str) -> str:
        return v or "translit"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    twilio_whatsapp_from: str = ""

    data_dir: Path = REPO_ROOT / "data"

    @property
    def demo_areas(self) -> tuple[str, str]:
        return (self.demo_area_1, self.demo_area_2)


@lru_cache
def get_settings() -> Settings:
    return Settings()
