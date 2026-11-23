"""LLM adapter: any OpenAI-compatible chat API (LLM_BASE_URL, LLM_MODEL, LLM_API_KEY).

Vaani doesn't depend on native tool calling. The model replies with ONE JSON object:

    {"say": "<words for the caller>", "actions": [{"tool": "<function>", "args": {...}}]}

That works on every provider (native tool calling on Featherless was failing when we
tested), and code validates every action before anything happens.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from openai import APIStatusError, APITimeoutError, AsyncOpenAI

Message = dict[str, Any]


@dataclass
class Action:
    tool: str
    args: dict[str, Any]


@dataclass
class LLMReply:
    say: str
    actions: list[Action]
    raw: str
    ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    parse_error: str | None = None


class LLM(Protocol):
    async def complete(self, messages: Sequence[Message]) -> LLMReply: ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


def parse_reply(raw: str) -> LLMReply:
    """Tolerant JSON parse: strips code fences / leading prose; falls back to plain speech."""
    text = _FENCE.sub("", raw.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1:
        return LLMReply(say=raw.strip(), actions=[], raw=raw, parse_error="no JSON object")
    if end <= start:  # cut-off JSON: never speak half an object to the caller
        return LLMReply(say="", actions=[], raw=raw, parse_error="truncated JSON")
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        return LLMReply(say="", actions=[], raw=raw, parse_error=f"bad JSON: {e.msg}")
    if not isinstance(obj, dict):
        return LLMReply(say="", actions=[], raw=raw, parse_error="JSON is not an object")
    actions: list[Action] = []
    for a in obj.get("actions") or []:
        if isinstance(a, dict) and isinstance(a.get("tool"), str):
            raw_args = a.get("args")
            actions.append(Action(a["tool"], raw_args if isinstance(raw_args, dict) else {}))
    say = obj.get("say")
    return LLMReply(say=say.strip() if isinstance(say, str) else "", actions=actions, raw=raw)


@dataclass
class OpenAICompatLLM:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 350
    timeout_s: float = 25.0
    retries: int = 2
    _client: AsyncOpenAI | None = field(default=None, init=False, repr=False)

    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                base_url=self.base_url, api_key=self.api_key, timeout=self.timeout_s, max_retries=0
            )
        return self._client

    async def complete(self, messages: Sequence[Message]) -> LLMReply:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            started = time.perf_counter()
            try:
                # cast: the SDK's overloads don't accept our plain dict messages
                completions = cast(Any, self.client().chat.completions)
                r = await completions.create(
                    model=self.model,
                    messages=list(messages),
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    response_format={"type": "json_object"},
                )
            except (APIStatusError, APITimeoutError) as e:
                last = e
                status = getattr(e, "status_code", 0)
                if status and status < 500 and status != 429:
                    raise
                await asyncio.sleep(0.6 * (attempt + 1))
                continue
            reply = parse_reply(r.choices[0].message.content or "")
            reply.ms = round((time.perf_counter() - started) * 1000)
            if r.usage:
                reply.prompt_tokens, reply.completion_tokens = r.usage.prompt_tokens, r.usage.completion_tokens
            return reply
        assert last is not None
        raise last


Script = dict[str, Any] | Callable[[Sequence[Message]], dict[str, Any]]


@dataclass
class ScriptedLLM:
    """Test double: returns the scripted replies in order (dicts, or callables of the messages)."""

    script: list[Script]
    calls: list[Sequence[Message]] = field(default_factory=list)

    async def complete(self, messages: Sequence[Message]) -> LLMReply:
        self.calls.append(list(messages))
        if not self.script:
            raise AssertionError("ScriptedLLM ran out of replies (unexpected LLM call)")
        step = self.script.pop(0)
        obj = step(messages) if callable(step) else step
        return parse_reply(json.dumps(obj, ensure_ascii=False))


def from_env(timeout_s: float | None = None, retries: int | None = None) -> OpenAICompatLLM:
    """Text mode (eval, CLI) keeps the patient defaults; voice passes a short timeout, because a
    caller can't wait 25 s (the provider sometimes stalls for 10–20 s)."""
    from backend.config import get_settings

    s = get_settings()
    if not (s.llm_base_url and s.llm_api_key and s.llm_model):
        raise SystemExit("Set LLM_BASE_URL, LLM_MODEL and LLM_API_KEY in .env")
    llm = OpenAICompatLLM(base_url=s.llm_base_url, api_key=s.llm_api_key, model=s.llm_model)
    if timeout_s is not None:
        llm.timeout_s = timeout_s
    if retries is not None:
        llm.retries = retries
    return llm
