# Project: ha-device-bridge
# Purpose: Local bridge that (1) discovers HA devices/entities, (2) exposes realtime status via API,
# (3) exposes adjustable properties, (4) lets clients set properties via commands.
# Stack: FastAPI + Uvicorn + SQLAlchemy (SQLite) + httpx + websockets
# Run: see README at end of this file.

# ──────────────────────────────────────────────────────────────────────────────
# File: docker-compose.yml
# ──────────────────────────────────────────────────────────────────────────────
version: "3.9"
services:
  bridge:
    build: .
    container_name: ha-device-bridge
    environment:
      - HA_URL=http://homeassistant.local:8123
      - HA_TOKEN=REPLACE_WITH_LONG_LIVED_TOKEN
      - DB_URL=sqlite:////data/bridge.db
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/data
    ports:
      - "8787:8787"
    restart: unless-stopped

# ──────────────────────────────────────────────────────────────────────────────
# File: Dockerfile
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8787
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]

# ──────────────────────────────────────────────────────────────────────────────
# File: requirements.txt
# ──────────────────────────────────────────────────────────────────────────────
fastapi==0.114.2
uvicorn[standard]==0.30.6
sqlalchemy==2.0.35
httpx==0.27.2
pydantic==2.9.2
pydantic-settings==2.6.1
websockets==12.0
orjson==3.10.7
sse-starlette==2.1.3
python-dotenv==1.0.1

# ──────────────────────────────────────────────────────────────────────────────
# File: app/settings.py
# ──────────────────────────────────────────────────────────────────────────────
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    HA_URL: str = "http://homeassistant.local:8123"
    HA_TOKEN: str
    DB_URL: str = "sqlite:///./data/bridge.db"
    LOG_LEVEL: str = "INFO"

settings = Settings()

# ──────────────────────────────────────────────────────────────────────────────
# File: app/db.py
# ──────────────────────────────────────────────────────────────────────────────
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .settings import settings

class Base(DeclarativeBase):
    pass

engine = create_engine(settings.DB_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# ──────────────────────────────────────────────────────────────────────────────
# File: app/models.py
# ──────────────────────────────────────────────────────────────────────────────
from sqlalchemy import Column, String, JSON, TIMESTAMP, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .db import Base

class Area(Base):
    __tablename__ = "areas"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True)

class Device(Base):
    __tablename__ = "devices"
    id = Column(String, primary_key=True)
    name = Column(String)
    manufacturer = Column(String)
    model = Column(String)
    area_id = Column(String, ForeignKey("areas.id"))
    hw_version = Column(String)
    sw_version = Column(String)
    identifiers = Column(JSON)
    connections = Column(JSON)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

class Entity(Base):
    __tablename__ = "entities"
    id = Column(String, primary_key=True)  # entity_id
    device_id = Column(String, ForeignKey("devices.id"))
    area_id = Column(String, ForeignKey("areas.id"))
    domain = Column(String, nullable=False)
    platform = Column(String)
    category = Column(String)
    name = Column(String)
    friendly_name = Column(String)
    state = Column(String)
    attributes = Column(JSON)
    unit = Column(String)
    last_changed = Column(TIMESTAMP)
    last_updated = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

class Alias(Base):
    __tablename__ = "aliases"
    entity_id = Column(String, ForeignKey("entities.id"), primary_key=True)
    alias = Column(String, primary_key=True)
    source = Column(String, default="user")

class Audit(Base):
    __tablename__ = "audit_log"
    id = Column(String, primary_key=True)
    ts = Column(TIMESTAMP, server_default=func.now())
    actor = Column(String)
    action = Column(String)
    target_type = Column(String)
    target_id = Column(String)
    payload = Column(JSON)

# ──────────────────────────────────────────────────────────────────────────────
# File: app/ha_client.py
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# File: app/mappings.py
# ──────────────────────────────────────────────────────────────────────────────
# Maps domain+property to service+payload merge rules.
# This enables a generic "set properties" API.
from typing import Dict, Any

# For example purposes; extend as needed.
DOMAIN_SERVICE_MAP: Dict[str, Dict[str, Any]] = {
    "light": {
        "on": ("light", "turn_on", lambda v: {} if v else ("light", "turn_off", {})),
        "brightness": ("light", "turn_on", lambda v: {"brightness": int(v)}),
        "color_temp": ("light", "turn_on", lambda v: {"color_temp": int(v)}),
        "hs_color": ("light", "turn_on", lambda v: {"hs_color": v}),
    },
    "switch": {
        "on": ("switch", "turn_on", lambda v: {} if v else ("switch", "turn_off", {})),
    },
    "climate": {
        "hvac_mode": ("climate", "set_hvac_mode", lambda v: {"hvac_mode": v}),
        "temperature": ("climate", "set_temperature", lambda v: {"temperature": float(v)}),
        "fan_mode": ("climate", "set_fan_mode", lambda v: {"fan_mode": v}),
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# File: app/sse.py
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# File: app/state.py
# ──────────────────────────────────────────────────────────────────────────────
import asyncio, logging, uuid
from typing import Dict, Any, List
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import SessionLocal, engine
from .models import Base, Area, Device, Entity, Alias, Audit
from .ha_client import ws_messages, list_states, list_services

log = logging.getLogger("state")

class Catalog:
    def __init__(self):
        self.services_cache: List[Dict[str, Any]] = []

    async def init_db(self):
        Base.metadata.create_all(engine)

    async def full_sync(self):
        # Hydrate entity states via REST
        states = await list_states()
        with SessionLocal() as s:
            for st in states:
                eid = st["entity_id"]
                attrs = st.get("attributes", {})
                ent = s.get(Entity, eid) or Entity(id=eid)
                ent.domain = eid.split(".",1)[0]
                ent.friendly_name = attrs.get("friendly_name")
                ent.attributes = attrs
                ent.state = st.get("state")
                s.merge(ent)
            s.commit()
        self.services_cache = await list_services()
        log.info("Full sync: %d entities, %d service domains", len(states), len(self.services_cache))

    async def ws_consumer(self, broadcast_cb):
        async for msg in ws_messages():
            # registry lists are returned once after subscribe; treat them as snapshots
            if msg.get("type") == "result" and isinstance(msg.get("result"), list):
                # area/device/entity registries
                # We only store areas minimally and entity->device bindings if available
                pass  # Simplified: core functionality relies on /api/states already

            if msg.get("type") == "event" and msg.get("event", {}).get("event_type") == "state_changed":
                ev = msg["event"]["data"]
                eid = ev["entity_id"]
                new_state = ev.get("new_state")
                if not new_state:
                    continue
                with SessionLocal() as s:
                    ent = s.get(Entity, eid) or Entity(id=eid)
                    ent.domain = eid.split(".",1)[0]
                    ent.state = new_state.get("state")
                    ent.attributes = new_state.get("attributes", {})
                    s.merge(ent)
                    s.commit()
                await broadcast_cb({"event":"state", "data":{"entity_id": eid, "state": ent.state, "attributes": ent.attributes}})

catalog = Catalog()

# ──────────────────────────────────────────────────────────────────────────────
# File: app/api.py
# ──────────────────────────────────────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models import Entity
from .mappings import DOMAIN_SERVICE_MAP
from .ha_client import call_service

router = APIRouter(prefix="/api/v1")

class PropertyRequest(BaseModel):
    entity_id: str
    properties: Dict[str, Any]
    actor: Optional[str] = "api"

@router.get("/entities")
def list_entities(q: Optional[str] = None, domain: Optional[str] = None):
    with SessionLocal() as s:
        stmt = select(Entity)
        rows = s.scalars(stmt).all()
        out = []
        for e in rows:
            if q and q.lower() not in (e.id.lower() + " " + (e.friendly_name or "").lower()):
                continue
            if domain and e.domain != domain:
                continue
            out.append({
                "entity_id": e.id,
                "domain": e.domain,
                "friendly_name": e.friendly_name,
                "state": e.state,
                "attributes": e.attributes,
            })
        return out

@router.get("/entities/{entity_id}")
def get_entity(entity_id: str):
    with SessionLocal() as s:
        e = s.get(Entity, entity_id)
        if not e:
            raise HTTPException(404, "Entity not found")
        return {
            "entity_id": e.id,
            "domain": e.domain,
            "friendly_name": e.friendly_name,
            "state": e.state,
            "attributes": e.attributes,
        }

@router.get("/properties/{entity_id}")
def get_adjustable_properties(entity_id: str):
    """Return a generic view of adjustable properties based on domain + attributes.
    This is heuristic; extend per your devices.
    """
    with SessionLocal() as s:
        e = s.get(Entity, entity_id)
        if not e:
            raise HTTPException(404, "Entity not found")
        props = {}
        if e.domain == "light":
            props["on"] = e.state != "off"
            if "brightness" in (e.attributes or {}):
                props["brightness"] = e.attributes.get("brightness")
            if "color_temp" in (e.attributes or {}):
                props["color_temp"] = e.attributes.get("color_temp")
            if "hs_color" in (e.attributes or {}):
                props["hs_color"] = e.attributes.get("hs_color")
        elif e.domain == "switch":
            props["on"] = e.state == "on"
        elif e.domain == "climate":
            for k in ("hvac_mode","temperature","fan_mode"):
                if k in (e.attributes or {}):
                    props[k] = e.attributes.get(k)
        # add more domains as needed
        return {"entity_id": e.id, "domain": e.domain, "properties": props}

@router.post("/command")
async def set_properties(req: PropertyRequest):
    # Determine domain
    domain = req.entity_id.split(".",1)[0]
    if domain not in DOMAIN_SERVICE_MAP:
        raise HTTPException(400, f"Domain {domain} not supported for generic set")

    # Accumulate service calls
    calls = []
    mapping = DOMAIN_SERVICE_MAP[domain]
    for prop, value in req.properties.items():
        if prop not in mapping:
            raise HTTPException(400, f"Property {prop} not supported for domain {domain}")
        entry = mapping[prop]
        if callable(entry[2]):
            payload = entry[2](value)
            if isinstance(payload, tuple):
                # mapper returned (domain, service, data)
                calls.append({"domain": payload[0], "service": payload[1], "data": {**payload[2], "entity_id": req.entity_id}})
            else:
                calls.append({"domain": entry[0], "service": entry[1], "data": {**payload, "entity_id": req.entity_id}})
        else:
            calls.append({"domain": entry[0], "service": entry[1], "data": {"entity_id": req.entity_id, **entry[2]}})

    results = []
    for c in calls:
        res = await call_service(c["domain"], c["service"], c["data"])
        results.append({"call": c, "result": res})
    return {"status": "ok", "results": results}

# ──────────────────────────────────────────────────────────────────────────────
# File: app/realtime.py
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# File: app/main.py
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# File: README.md
# ──────────────────────────────────────────────────────────────────────────────
# HA Device Bridge

A small, privacy-first bridge that:

1. **Discovers devices/entities** from Home Assistant
2. **Exposes realtime status** over SSE and REST
3. **Exposes adjustable properties** per entity (heuristic capabilities)
4. **Provides a command API** to set properties (maps to HA services)

## Quick start

1. Create a **Long-Lived Access Token** in Home Assistant for a non-admin user.
2. Copy `.env.example` to `.env` or set env vars in `docker-compose.yml`.
3. `docker compose up --build`
4. Open `http://localhost:8787/` → `{ status: ok }`

### Environment
- `HA_URL` (default `http://homeassistant.local:8123`)
- `HA_TOKEN` (required)
- `DB_URL` (default `sqlite:////data/bridge.db`)
- `LOG_LEVEL` (default `INFO`)

## API

- `GET /api/v1/entities?[q=]&[domain=]` → list entities with state/attributes
- `GET /api/v1/entities/{entity_id}` → single entity
- `GET /api/v1/properties/{entity_id}` → adjustable properties (domain-based)
- `POST /api/v1/command` → set properties
  ```json
  {
    "entity_id": "light.kitchen_ceiling",
    "properties": {"on": true, "brightness": 180},
    "actor": "ui"
  }
  ```
- `GET /api/v1/status/stream` → **SSE** stream of `{event: "state", data: {entity_id, state, attributes}}`

## Notes
- This starter focuses on entities/state. Area/device registry snapshots are easy to add (handlers already scaffolded).
- Extend `mappings.py` for more domains (fans, covers, media_player, etc.).
- For richer capability discovery, cache `/api/services` and surface schemas.

## Security
- Run with a **scoped HA user**. Consider reverse proxy + auth for the bridge.
- Add allowlists/blocklists before exposing beyond localhost.

## Local LLM integration
- Tool calling: define tools that hit these endpoints.
- DSL: instruct the model to output `/service domain.service entity_id=... key=val` and POST to a small `/dsl` you can add.

## Roadmap ideas
- Persist area/device registries with proper relations
- WebSocket passthrough endpoint for clients (mirror HA events)
- History endpoints (query HA recorder or maintain your own)
- UI scaffolding (Next.js dashboard) — can be generated on request
