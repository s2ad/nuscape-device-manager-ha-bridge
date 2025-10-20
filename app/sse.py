from sse_starlette.sse import EventSourceResponse
from typing import AsyncIterator
import asyncio, json

async def sse_stream(generator: AsyncIterator[dict]):
    async def event_publisher():
        async for ev in generator:
            yield {
                "event": ev.get("event", "message"),
                "data": json.dumps(ev["data"]) if "data" in ev else json.dumps(ev)
            }
            await asyncio.sleep(0)
    return EventSourceResponse(event_publisher())