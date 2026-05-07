"""
Nexus Chat — Real-Time Multi-User Chat
FastAPI + Supabase + WebSockets

Demonstrates:
  - Concurrent WebSocket connection handling (asyncio)
  - Parallel DB + broadcast with asyncio.gather()
  - Background cleanup worker (asyncio.create_task)
  - Shared persistent state via Supabase PostgreSQL
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import database as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("nexus")


# ──────────────────────────────────────────────
# Connection Manager — handles concurrent clients
# ──────────────────────────────────────────────

class ConnectionManager:
    """
    Manages all active WebSocket connections concurrently.
    Uses asyncio.Lock for thread-safe mutations and
    asyncio.gather() for parallel broadcasts.
    """

    def __init__(self):
        self._connections: dict[str, WebSocket] = {}  # user_id → ws
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[user_id] = ws
        log.info(f"[+] {user_id} connected ({self.count} total)")

    async def disconnect(self, user_id: str) -> None:
        async with self._lock:
            self._connections.pop(user_id, None)
        log.info(f"[-] {user_id} disconnected ({self.count} total)")

    async def send(self, user_id: str, payload: dict) -> None:
        async with self._lock:
            ws = self._connections.get(user_id)
        if ws:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.disconnect(user_id)

    async def broadcast(self, payload: dict, exclude: str | None = None) -> None:
        """
        Concurrent broadcast — sends to all clients in parallel via asyncio.gather().
        Failed sends are caught per-client without blocking others.
        """
        async with self._lock:
            targets = [(uid, ws) for uid, ws in self._connections.items() if uid != exclude]

        async def _safe_send(uid: str, ws: WebSocket):
            try:
                await ws.send_json(payload)
            except Exception:
                await self.disconnect(uid)

        # All sends fire concurrently — true parallel I/O
        await asyncio.gather(*[_safe_send(uid, ws) for uid, ws in targets])

    @property
    def count(self) -> int:
        return len(self._connections)

    @property
    def user_ids(self) -> list[str]:
        return list(self._connections.keys())


manager = ConnectionManager()


# ──────────────────────────────────────────────
# Background Workers
# ──────────────────────────────────────────────

async def presence_cleanup_worker():
    """
    Background worker: removes stale presence rows every 10s.
    Runs as an independent asyncio task — simulates a distributed worker.
    """
    log.info("[worker] presence_cleanup started")
    while True:
        await asyncio.sleep(10)
        try:
            removed = await asyncio.to_thread(db.cleanup_stale_presence)
            if removed:
                log.info(f"[worker] cleaned {removed} stale presence rows")
                # Notify all clients of updated user list
                users = await asyncio.to_thread(db.get_online_users)
                await manager.broadcast({
                    "event": "presence_update",
                    "users": users,
                    "online_count": manager.count,
                })
        except Exception as e:
            log.error(f"[worker] cleanup error: {e}")


# ──────────────────────────────────────────────
# App Lifecycle
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(presence_cleanup_worker())
    log.info("[startup] Nexus Chat server ready")
    yield
    log.info("[shutdown] Nexus Chat server stopped")


app = FastAPI(title="Nexus Chat", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ──────────────────────────────────────────────
# HTTP Routes
# ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()


@app.get("/api/stats")
async def stats():
    """Live server stats endpoint."""
    msgs = await asyncio.to_thread(db.get_messages, limit=1)
    users = await asyncio.to_thread(db.get_online_users)
    return {
        "ws_connections": manager.count,
        "online_users": len(users),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


# ──────────────────────────────────────────────
# WebSocket Endpoint
# ──────────────────────────────────────────────

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(user_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            event = data.get("event")

            # ── JOIN ──────────────────────────────────
            if event == "join":
                user = data["user"]

                # Concurrent: upsert presence + fetch history in parallel
                msgs, _ = await asyncio.gather(
                    asyncio.to_thread(db.get_messages),
                    asyncio.to_thread(db.upsert_presence, user),
                )
                users = await asyncio.to_thread(db.get_online_users)

                # Send full history + current roster to the joining client
                await manager.send(user_id, {
                    "event": "init",
                    "messages": msgs,
                    "users": users,
                    "online_count": manager.count,
                })

                # Notify everyone else
                await manager.broadcast({
                    "event": "user_joined",
                    "user": user,
                    "users": users,
                    "online_count": manager.count,
                }, exclude=user_id)

                log.info(f"[join] {user['name']} — {manager.count} online")

            # ── MESSAGE ───────────────────────────────
            elif event == "message":
                msg = data["message"]

                # Concurrent: save to DB + broadcast to all clients in parallel
                save_task = asyncio.to_thread(db.save_message, msg)
                broadcast_task = manager.broadcast({
                    "event": "message",
                    "message": msg,
                })
                await asyncio.gather(save_task, broadcast_task)

                log.info(f"[msg] {msg['name']}: {msg['text'][:60]}")

            # ── HEARTBEAT ─────────────────────────────
            elif event == "heartbeat":
                user = data["user"]
                await asyncio.to_thread(db.upsert_presence, user)
                users = await asyncio.to_thread(db.get_online_users)

                # Broadcast updated presence to everyone
                await manager.broadcast({
                    "event": "presence_update",
                    "users": users,
                    "online_count": manager.count,
                })

    except WebSocketDisconnect:
        await manager.disconnect(user_id)

        # Remove presence and notify others
        await asyncio.to_thread(db.remove_presence, user_id)
        users = await asyncio.to_thread(db.get_online_users)

        await manager.broadcast({
            "event": "user_left",
            "user_id": user_id,
            "users": users,
            "online_count": manager.count,
        })

    except Exception as e:
        log.error(f"[ws error] {user_id}: {e}")
        await manager.disconnect(user_id)


# ──────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
