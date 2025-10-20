import asyncio, logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .settings import settings
from .state import catalog
from .api import router as api_router
from .realtime import broadcaster
from .sse import sse_stream

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, "INFO"))

app = FastAPI(title="HA Device Bridge", version="0.1.0")
app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def on_start():
    await catalog.init_db()

    async def do_full_sync_with_retry():
        import asyncio, logging
        log = logging.getLogger("startup")
        delay = 2
        while True:
            try:
                await catalog.full_sync()
                log.info("Initial full_sync succeeded")
                return
            except Exception as e:
                log.warning("full_sync failed: %s; retrying in %ss", e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    # Kick off full sync in the background so startup doesn't crash on DNS/connectivity issues
    asyncio.create_task(do_full_sync_with_retry())

    async def _broadcast(ev):
        await broadcaster.broadcast(ev)
    asyncio.create_task(catalog.ws_consumer(_broadcast))

@app.get("/api/v1/status/stream")
async def stream():
    # wrap broadcaster.register() so it becomes an async generator,
    # and return EventSourceResponse directly (not a coroutine).
    from .sse import EventSourceResponse

    async def event_generator():
        async for ev in broadcaster.register():
            yield ev

    return EventSourceResponse(event_generator(), ping=15)

@app.get("/")
def root():
    return {"name":"ha-device-bridge","status":"ok"}