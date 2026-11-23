"""Tool plumbing: context, errors, registry and the runner every tool call goes through.

The runner validates arguments against the tool's Pydantic model (the same model becomes
the LLM's JSON schema in Phase 3), times the call, appends it to the call's tool timeline
and emits a `tool_called` event with a human-readable summary (CONTRACTS.md §2).
"""

from __future__ import annotations

import time as _time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from backend.catalog.models import Catalog
from backend.clock import in_window, iso_ts, window
from backend.config import Settings
from backend.messaging import Messenger
from backend.store import Store

Result = dict[str, Any]


class ToolError(Exception):
    """A rule said no. `code` is from CONTRACTS.md §2; the flow turns it into speech."""

    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.extra = extra


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass
class ToolContext:
    store: Store
    catalog: Catalog
    settings: Settings
    messenger: Messenger
    call_id: str | None = None
    phone: str | None = None  # caller ID; never asked from the caller
    language: str = "en"  # te | hi | en
    timeline: list[Result] = field(default_factory=list)
    # Extra in-process listeners (the voice test page); the DB event is always written first.
    listeners: list[Callable[[str, dict[str, Any]], Awaitable[None]]] = field(default_factory=list)

    async def emit(self, type_: str, payload: dict[str, Any]) -> None:
        """Write a call event (call_events → Supabase Realtime) and tell any listeners."""
        if not self.call_id:
            return
        await self.store.emit(self.call_id, type_, payload)
        for listener in self.listeners:
            await listener(type_, payload)


ToolFn = Callable[[ToolContext, Any], Awaitable[tuple[Result, str]]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args: type[Args]
    fn: ToolFn


REGISTRY: dict[str, ToolSpec] = {}


def tool(name: str, args: type[Args], description: str) -> Callable[[ToolFn], ToolFn]:
    """Register a tool. The function returns (result, summary)."""

    def deco(fn: ToolFn) -> ToolFn:
        REGISTRY[name] = ToolSpec(name, description, args, fn)
        return fn

    return deco


async def run_tool(ctx: ToolContext, name: str, raw_args: dict[str, Any] | None = None) -> Result:
    spec = REGISTRY.get(name)
    if spec is None:
        return {"ok": False, "error": "UNKNOWN_TOOL", "message": f"No tool {name}"}
    started = _time.perf_counter()
    raw_args = dict(raw_args or {})
    try:
        args = spec.args.model_validate(raw_args)
        result, summary = await spec.fn(ctx, args)
        result = {"ok": True, **result}
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        result = {"ok": False, "error": "INVALID_ARGS", "message": problems}
        summary = f"{name} → invalid arguments"
    except ToolError as e:
        result = {"ok": False, "error": e.code, "message": e.message, **e.extra}
        summary = f"{name} → {e.code.lower().replace('_', ' ')}"
    ms = round((_time.perf_counter() - started) * 1000)
    ctx.timeline.append(
        {"ts": iso_ts(), "tool": name, "args": raw_args, "result": result, "summary": summary, "ms": ms}
    )
    await ctx.emit("tool_called", {"tool": name, "summary": summary, "ms": ms, "ok": result["ok"]})
    return result


# ---------------------------------------------------------------------------
# Shared validators used by several tools
# ---------------------------------------------------------------------------


def require_window(d: date) -> None:
    if not in_window(d):
        lo, hi = window()
        raise ToolError(
            "DATE_OUT_OF_RANGE",
            f"We can book from {lo.isoformat()} to {hi.isoformat()}",
            earliest=lo.isoformat(),
            latest=hi.isoformat(),
        )


def require_area(ctx: ToolContext, area_id: str) -> str:
    known = {a.area_id: a.name_en for a in ctx.catalog.areas}
    if area_id not in known or area_id not in ctx.settings.demo_areas:
        raise ToolError("UNSUPPORTED_AREA", f"{area_id} is not a demo area", supported=list(ctx.settings.demo_areas))
    return known[area_id]


def day_word(d: date) -> str:
    """'today' / 'tomorrow' / 'Sat 28 Nov' for summaries."""
    lo, _ = window()
    delta = (d - lo).days
    return {0: "today", 1: "tomorrow"}.get(delta, d.strftime("%a %d %b"))
