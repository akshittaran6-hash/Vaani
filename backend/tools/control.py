"""Call-control tools: switch_service, transfer_to_human, end_call.

They don't change data; they record intent on the timeline so the flow (Phase 3) and the
Studio can act on it.
"""

from __future__ import annotations

from typing import Literal

from backend.tools.base import Args, Result, ToolContext, tool


class SwitchServiceArgs(Args):
    to: Literal["restaurant", "hospital"]
    reason: str = ""


@tool("switch_service", SwitchServiceArgs, "Move the caller to the other service; name, phone and language carry over.")
async def switch_service(ctx: ToolContext, a: SwitchServiceArgs) -> tuple[Result, str]:
    if ctx.call_id:
        await ctx.emit("agent_switched", {"to": a.to, "reason": a.reason})
    return {"service": a.to}, f"Switched to {a.to} agent"


class ReasonArgs(Args):
    reason: str = ""


@tool("transfer_to_human", ReasonArgs, "Caller asked for a person: log a callback request.")
async def transfer_to_human(ctx: ToolContext, a: ReasonArgs) -> tuple[Result, str]:
    return {
        "callback_requested": True,
        "reason": a.reason,
    }, f"Callback requested ({a.reason or 'caller asked for a person'})"


@tool("end_call", ReasonArgs, "End the call politely.")
async def end_call(ctx: ToolContext, a: ReasonArgs) -> tuple[Result, str]:
    return {"end": True, "reason": a.reason}, f"Call ending ({a.reason or 'done'})"
