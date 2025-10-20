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