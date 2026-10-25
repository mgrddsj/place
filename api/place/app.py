"""FastAPI app: /ws is the port of the API Gateway WebSocket API (v3)."""
from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from .config import Settings, load_settings
from .hub import Hub
from .pixels import parse_draw
from .rate_limit import evaluate
from .store import RedisStore, Store

HISTORY_REPLY_LIMIT = 1000


def create_app(settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    settings = settings or load_settings()
    store = store or RedisStore(settings.redis_url, settings.events_stream)
    hub = Hub()
    started_at = time.monotonic()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await store.ensure_group(settings.consumer_group)
        try:
            yield
        finally:
            await store.close()

    app = FastAPI(title="place", version="4.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.hub = hub

    async def handle_message(raw: str, websocket: WebSocket) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.send_text(json.dumps({"type": "error", "error": "invalid_json"}))
            return
        if not isinstance(payload, dict):
            await websocket.send_text(json.dumps({"type": "error", "error": "invalid_frame"}))
            return

        action = payload.get("action")
        client_id = payload.get("clientId") or ""

        if action == "checkRateLimit":
            next_ms = await store.get_cooldown(client_id)
            await websocket.send_text(json.dumps({"type": "rateLimit", "nextAvailableTime": next_ms}))
            return

        if action == "getHistory":
            events = [json.loads(item) for item in await store.history(HISTORY_REPLY_LIMIT)]
            await websocket.send_text(json.dumps({"type": "history", "events": events}))
            return

        if action != "draw":
            await websocket.send_text(json.dumps({"type": "error", "error": "unknown_action"}))
            return

        draw = parse_draw(payload, settings.image_size)
        if draw is None:
            await websocket.send_text(json.dumps({"type": "error", "error": "invalid_draw"}))
            return

        decision = evaluate(
            now_ms=int(time.time() * 1000),
            stored_next_ms=await store.get_cooldown(client_id),
            cooldown_ms=settings.cooldown_ms,
            whitelisted=client_id in settings.admin_client_ids,
        )
        if not decision.allowed:
            await websocket.send_text(json.dumps({
                "type": "error",
                "error": "rate_limited",
                "nextAvailableTime": decision.next_available_ms,
            }))
            return

        await store.set_cooldown(
            client_id, decision.next_available_ms, settings.rate_limit_seconds + 60
        )
        body = json.dumps(draw.to_json())
        await store.append_history(body)
        await store.publish_event({
            "x": str(draw.x),
            "y": str(draw.y),
            "r": str(draw.r),
            "g": str(draw.g),
            "b": str(draw.b),
        })
        await hub.broadcast(body)  # sender included, exactly like v3
        await websocket.send_text(json.dumps({
            "type": "rateLimit",
            "nextAvailableTime": decision.next_available_ms,
        }))

    async def prune_stale_clients() -> None:
        """Drop ids left behind by clients that vanished without a clean close.

        The hub is authoritative: this process holds every live socket, so an id in the
        store without a socket is stale. Safe only because `api` runs as one replica.
        """
        live = set(hub.ids())
        for stored_id in await store.clients():
            if stored_id not in live:
                await store.remove_client(stored_id)

    @app.get("/healthz")
    async def healthz():
        redis_ok = await store.ping()
        payload = {
            "status": "ok" if redis_ok else "degraded",
            "redis": redis_ok,
            "online": len(await store.clients()),
            "uptime_s": round(time.monotonic() - started_at),
        }
        return JSONResponse(payload, status_code=200 if redis_ok else 503)

    @app.get("/place.png")
    async def place_png():
        if not settings.place_png.exists():
            return JSONResponse({"error": "no image yet"}, status_code=404)
        return FileResponse(
            settings.place_png,
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        connection_id = f"conn_{uuid.uuid4().hex[:12]}"
        # Register locally first, so a concurrent connect cannot prune this id as stale.
        hub.add(connection_id, websocket)
        await store.add_client(connection_id)
        await prune_stale_clients()
        try:
            while True:
                raw = await websocket.receive_text()
                await handle_message(raw, websocket)
        except WebSocketDisconnect:
            pass
        finally:
            hub.remove(connection_id)
            await store.remove_client(connection_id)

    return app


app = create_app()
