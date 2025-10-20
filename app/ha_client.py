import asyncio, json, logging, time
import httpx, websockets
from websockets.exceptions import ConnectionClosed
from typing import AsyncIterator, Dict, Any
from .settings import settings

log = logging.getLogger("ha")

AUTH_HEADERS = {"Authorization": f"Bearer {settings.HA_TOKEN}", "Content-Type": "application/json"}

async def rest_get(path: str):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{settings.HA_URL}{path}", headers=AUTH_HEADERS, timeout=15)
        r.raise_for_status()
        return r.json()

async def rest_post(path: str, data: Dict[str, Any]):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{settings.HA_URL}{path}", headers=AUTH_HEADERS, timeout=15, content=json.dumps(data))
        r.raise_for_status()
        return r.json()

async def ws_messages() -> AsyncIterator[Dict[str, Any]]:
    url = settings.HA_URL.replace("http", "ws") + "/api/websocket"
    while True:
        try:
            async with websockets.connect(url) as ws:
                # handshake
                msg = json.loads(await ws.recv())
                assert msg["type"] == "auth_required"
                await ws.send(json.dumps({"type":"auth", "access_token": settings.HA_TOKEN}))
                ok = json.loads(await ws.recv())
                assert ok["type"] == "auth_ok"

                # subscribe to events
                msg_id = 1
                async def send(obj):
                    nonlocal msg_id
                    obj["id"] = msg_id; msg_id += 1
                    await ws.send(json.dumps(obj))

                await send({"type":"subscribe_events","event_type":"state_changed"})
                await send({"type":"area_registry/list"})
                await send({"type":"device_registry/list"})
                await send({"type":"entity_registry/list"})

                while True:
                    raw = await ws.recv()
                    yield json.loads(raw)
        except (ConnectionClosed, OSError) as e:
            log.warning("WS disconnected: %s; retrying in 2s", e)
            await asyncio.sleep(2)

# convenience helpers
async def list_states():
    return await rest_get("/api/states")

async def list_services():
    return await rest_get("/api/services")

async def call_service(domain: str, service: str, data: Dict[str, Any]):
    return await rest_post(f"/api/services/{domain}/{service}", data)