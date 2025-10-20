import asyncio
from typing import AsyncIterator, Callable

class Broadcaster:
    def __init__(self):
        self._queues = set()

    async def register(self) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._queues.discard(q)

    async def broadcast(self, event: dict):
        for q in list(self._queues):
            await q.put(event)

broadcaster = Broadcaster()