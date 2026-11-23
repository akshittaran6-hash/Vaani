"""FallbackLLM: Groq's free tier first, the second provider when it fails or rate-limits."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from backend.voice.llm import FallbackLLM, LLMReply, Message, OpenAICompatLLM


class RateLimited(Exception):
    status_code = 429


class FakeLLM(OpenAICompatLLM):
    def __init__(self, name: str, fail: Exception | None = None) -> None:
        super().__init__(base_url="http://x", api_key="k", model=name)
        self.fail = fail
        self.calls = 0

    async def complete(self, messages: Sequence[Message]) -> LLMReply:
        self.calls += 1
        if self.fail:
            raise self.fail
        return LLMReply(say=self.model, actions=[], raw="{}")


async def test_primary_used_when_healthy() -> None:
    p, f = FakeLLM("groq"), FakeLLM("featherless")
    r = await FallbackLLM([p, f]).complete([])
    assert r.say == "groq" and f.calls == 0


async def test_429_falls_back_and_skips_primary_for_a_while() -> None:
    p, f = FakeLLM("groq", RateLimited("rate limit")), FakeLLM("featherless")
    llm = FallbackLLM([p, f], cooldown_s=60)
    assert (await llm.complete([])).say == "featherless"
    assert (await llm.complete([])).say == "featherless"
    assert p.calls == 1  # second call didn't pay for another refused request


async def test_other_errors_fall_back_without_cooldown() -> None:
    p, f = FakeLLM("groq", TimeoutError("slow")), FakeLLM("featherless")
    llm = FallbackLLM([p, f])
    await llm.complete([])
    await llm.complete([])
    assert p.calls == 2 and f.calls == 2


def test_from_env_builds_fallback(monkeypatch: Any) -> None:
    from backend import config
    from backend.voice import llm as llm_mod

    s = config.Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm_base_url="https://api.groq.com/openai/v1",
        llm_model="qwen/qwen3.8-27b@none, openai/gpt-oss-120b",
        llm_api_key="k1",
        llm_reasoning_effort="low",
        llm_fallback_base_url="https://api.featherless.ai/v1",
        llm_fallback_model="Qwen/Qwen3-30B-A3B-Instruct-2507",
        llm_fallback_api_key="k2",
    )
    monkeypatch.setattr(config, "get_settings", lambda: s)
    built = llm_mod.from_env(timeout_s=4.5, retries=1)
    assert isinstance(built, FallbackLLM)
    assert [x.model for x in built.chain] == [
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-120b",
        "Qwen/Qwen3-30B-A3B-Instruct-2507",
    ]
    assert built.chain[0].extra_body == {"reasoning_effort": "none"} and built.chain[0].retries == 0
    assert built.chain[1].extra_body == {"reasoning_effort": "low"}  # LLM_REASONING_EFFORT default
    assert built.chain[-1].extra_body == {} and built.chain[-1].timeout_s == 4.5 and built.chain[-1].retries == 1
    # earlier links give up fast (a hung free-tier model mustn't stack timeouts before the fallback)
    assert all(x.timeout_s == 3.0 for x in built.chain[:-1])


async def test_three_model_chain_skips_cooling_models() -> None:
    a, b, c = FakeLLM("a", RateLimited()), FakeLLM("b", RateLimited()), FakeLLM("c")
    llm = FallbackLLM([a, b, c], cooldown_s=60)
    assert (await llm.complete([])).say == "c"
    assert (await llm.complete([])).say == "c" and (a.calls, b.calls) == (1, 1)
