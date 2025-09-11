import asyncio
from collections import defaultdict
from typing import AsyncIterator, Dict, List

class ChannelBroker:
    """
    Simple pub/sub per device_id for SSE.
    Each subscriber gets its own asyncio.Queue.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        async with self._lock:
            self._subscribers[channel].append(q)
        return q

    async def unsubscribe(self, channel: str, q: asyncio.Queue):
        async with self._lock:
            if channel in self._subscribers and q in self._subscribers[channel]:
                self._subscribers[channel].remove(q)

    async def publish(self, channel: str, message: dict):
        async with self._lock:
            queues = list(self._subscribers.get(channel, []))
        for q in queues:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                # Drop oldest if needed
                _ = q.get_nowait()
                await q.put(message)

broker = ChannelBroker()
