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
