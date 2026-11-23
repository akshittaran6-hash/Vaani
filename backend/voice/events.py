"""In-process event hub for the voice test page (Server-Sent Events, keyed by peer connection).

The websites get the same events from Supabase Realtime (call_events); this hub only lets
/voice-test show the live transcript and latency without a Supabase project.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

_queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)


def subscribe(key: str) -> asyncio.Queue[dict[str, Any]]:
    q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)
    _queues[key].append(q)
    return q


def unsubscribe(key: str, q: asyncio.Queue[dict[str, Any]]) -> None:
    if q in _queues.get(key, []):
        _queues[key].remove(q)
    if not _queues.get(key):
        _queues.pop(key, None)


async def publish(key: str, type_: str, payload: dict[str, Any]) -> None:
    for q in list(_queues.get(key, [])):
        if not q.full():
            q.put_nowait({"type": type_, "payload": payload})
