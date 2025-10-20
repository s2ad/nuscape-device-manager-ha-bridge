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
                # Extract fields before closing session to avoid DetachedInstanceError
                state_val = new_state.get("state")
                attrs_val = new_state.get("attributes", {})

                with SessionLocal() as s:
                    ent = s.get(Entity, eid) or Entity(id=eid)
                    ent.domain = eid.split(".",1)[0]
                    ent.state = state_val
                    ent.attributes = attrs_val
                    s.merge(ent)
                    s.commit()

                # Now broadcast using plain dicts, not ORM object
                await broadcast_cb({
                    "event": "state",
                    "data": {
                        "entity_id": eid,
                        "state": state_val,
                        "attributes": attrs_val,
                    },
                })

catalog = Catalog()