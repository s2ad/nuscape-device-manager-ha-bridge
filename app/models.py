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