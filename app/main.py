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
    await catalog.full_sync()
    async def _broadcast(ev):
        await broadcaster.broadcast(ev)
    asyncio.create_task(catalog.ws_consumer(_broadcast))

@app.get("/api/v1/status/stream")
async def stream():
    return await sse_stream(broadcaster.register())

@app.get("/")
def root():
    return {"name":"ha-device-bridge","status":"ok"}