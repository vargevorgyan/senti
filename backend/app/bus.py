"""In-process pub/sub for Server-Sent Events (device profile pushes and the admin live feed)."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict


class Bus:
    def __init__(self):
        self.subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self.loop: asyncio.AbstractEventLoop | None = None

    def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.subs[channel].add(q)
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        self.subs[channel].discard(q)

    def publish(self, channel: str, data: dict) -> None:
        """Thread-safe: sync endpoints run in a worker thread."""
        msg = json.dumps(data, default=str)
        loop = self.loop
        for q in list(self.subs.get(channel, ())):
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(_put, q, msg)
            else:
                _put(q, msg)


def _put(q: asyncio.Queue, msg: str) -> None:
    try:
        q.put_nowait(msg)
    except asyncio.QueueFull:
        pass


bus = Bus()


async def sse(q: asyncio.Queue, hello: dict | None = None):
    if hello:
        yield f"data: {json.dumps(hello)}\n\n"
    while True:
        try:
            msg = await asyncio.wait_for(q.get(), timeout=15)
            yield f"data: {msg}\n\n"
        except asyncio.TimeoutError:
            yield ": keepalive\n\n"
