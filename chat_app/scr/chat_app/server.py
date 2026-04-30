"""
Chat_Room — FastAPI WebSocket server
====================================
Bridges the browser (WebSocket / REST) with:
  - CloudAMQP / RabbitMQ  (real-time pub/sub via pika)
  - Supabase              (rooms & messages persistence via httpx)

Run:
    cd chat_app/scr
    uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pika
import pika.exceptions
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# ── Environment ───────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent.parent.parent / ".env")

AMQP_URL       = os.getenv("AMQP_URL", "amqp://localhost")
SUPABASE_URL   = os.getenv("SUPABASE_URL", "https://jgzphwjbwwbnomqpdpzr.supabase.co")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY", "sb_publishable_8IY3AeHhu0x4iTV_kIvaWA_zRm23-eP")

EXCHANGE       = "chat.topic"
STATIC_DIR     = Path(__file__).parent / "static"

SB_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation",
}

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="Chat_Room API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Supabase helpers ──────────────────────────────────────────────────────────

async def sb_get(path: str, params: dict | None = None) -> Any:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{path}",
            headers=SB_HEADERS,
            params=params or {},
        )
        r.raise_for_status()
        return r.json()


async def sb_post(path: str, body: dict) -> Any:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/{path}",
            headers=SB_HEADERS,
            json=body,
        )
        r.raise_for_status()
        if r.status_code == 204:
            return None
        return r.json()


async def sb_delete(path: str, params: dict) -> None:
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{SUPABASE_URL}/rest/v1/{path}",
            headers=SB_HEADERS,
            params=params,
        )
        r.raise_for_status()


# ── RabbitMQ helpers ──────────────────────────────────────────────────────────

def _make_connection() -> pika.BlockingConnection:
    params = pika.URLParameters(AMQP_URL)
    conn   = pika.BlockingConnection(params)
    return conn


def _declare_exchange(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    channel.exchange_declare(
        exchange      = EXCHANGE,
        exchange_type = "topic",
        durable       = True,
    )


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/api/rooms")
async def list_rooms():
    rows = await sb_get("rooms", {"select": "name", "order": "created_at.asc"})
    return [r["name"] for r in rows]


@app.post("/api/rooms", status_code=201)
async def create_room(payload: dict):
    name = payload.get("name", "").strip().upper()
    if not name:
        raise HTTPException(status_code=422, detail="Room name is required")
    try:
        result = await sb_post("rooms", {"name": name})
        return result
    except httpx.HTTPStatusError as e:
        body = e.response.json()
        msg  = body.get("message", str(e))
        if "unique" in msg.lower() or "duplicate" in msg.lower():
            raise HTTPException(status_code=409, detail="Room already exists")
        raise HTTPException(status_code=e.response.status_code, detail=msg)


@app.delete("/api/rooms/{name}", status_code=204)
async def delete_room(name: str):
    name = name.upper()
    await sb_delete("messages", {"room_name": f"eq.{name}"})
    await sb_delete("rooms",    {"name":      f"eq.{name}"})


@app.get("/api/rooms/{name}/history")
async def room_history(name: str):
    name = name.upper()
    rows = await sb_get(
        "messages",
        {
            "select":    "username,text,timestamp",
            "room_name": f"eq.{name}",
            "order":     "timestamp.asc",
            "limit":     "200",
        },
    )
    return rows


# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    """Tracks active WebSocket clients per room."""

    def __init__(self):
        # room → set of websockets
        self._rooms: dict[str, set[WebSocket]] = {}

    def add(self, room: str, ws: WebSocket) -> None:
        self._rooms.setdefault(room, set()).add(ws)

    def remove(self, room: str, ws: WebSocket) -> None:
        self._rooms.get(room, set()).discard(ws)

    async def broadcast(self, room: str, data: dict, exclude: WebSocket | None = None) -> None:
        payload = json.dumps(data)
        dead    = []
        for ws in list(self._rooms.get(room, set())):
            if ws is exclude:
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove(room, ws)

    async def send(self, ws: WebSocket, data: dict) -> None:
        try:
            await ws.send_text(json.dumps(data))
        except Exception:
            pass


manager = ConnectionManager()

# ── RabbitMQ consumer per room (runs in a background thread) ──────────────────

# active consumer threads per room
_consumer_threads: dict[str, threading.Thread] = {}


def _start_room_consumer(room: str, loop: asyncio.AbstractEventLoop) -> None:
    """
    Starts a dedicated pika consumer thread for `room`.
    Incoming messages are forwarded to all WebSocket clients via asyncio.
    """
    if room in _consumer_threads and _consumer_threads[room].is_alive():
        return  # already running

    def run():
        while True:
            try:
                conn    = _make_connection()
                channel = conn.channel()
                _declare_exchange(channel)

                result     = channel.queue_declare(queue="", exclusive=True)
                queue_name = result.method.queue
                channel.queue_bind(
                    exchange    = EXCHANGE,
                    queue       = queue_name,
                    routing_key = f"room.{room}",
                )

                def on_message(ch, method, properties, body):
                    text = body.decode("utf-8", errors="replace")
                    if ": " in text:
                        sender, msg = text.split(": ", 1)
                    else:
                        sender, msg = "?", text

                    payload = {
                        "type":      "message",
                        "username":  sender,
                        "text":      msg,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "room":      room,
                    }

                    # schedule Supabase save + broadcast on the main asyncio loop
                    asyncio.run_coroutine_threadsafe(
                        _save_and_broadcast(room, payload),
                        loop,
                    )

                channel.basic_consume(
                    queue               = queue_name,
                    on_message_callback = on_message,
                    auto_ack            = True,
                )
                channel.start_consuming()

            except pika.exceptions.AMQPConnectionError:
                import time
                time.sleep(3)
                continue
            except Exception:
                break

    t = threading.Thread(target=run, daemon=True, name=f"consumer-{room}")
    t.start()
    _consumer_threads[room] = t


async def _save_and_broadcast(room: str, payload: dict) -> None:
    """Persist message to Supabase, then broadcast to all WS clients in room."""
    try:
        await sb_post("messages", {
            "room_name": room,
            "username":  payload["username"],
            "text":      payload["text"],
            "timestamp": payload["timestamp"],
        })
    except Exception as e:
        print(f"[supabase] save error: {e}")

    await manager.broadcast(room, payload)


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws/{room}/{username}")
async def ws_chat(ws: WebSocket, room: str, username: str):
    room     = room.strip().upper()
    username = username.strip().title()

    await ws.accept()
    manager.add(room, ws)

    # ensure consumer is running for this room
    loop = asyncio.get_event_loop()
    _start_room_consumer(room, loop)

    # notify client of successful connection
    await manager.send(ws, {"type": "connected", "room": room, "username": username})

    # publisher connection (one per WS session, opened lazily)
    pub_conn: pika.BlockingConnection | None = None
    pub_ch:   pika.adapters.blocking_connection.BlockingChannel | None = None

    def get_publisher():
        nonlocal pub_conn, pub_ch
        if pub_conn is None or not pub_conn.is_open:
            pub_conn = _make_connection()
            pub_ch   = pub_conn.channel()
            _declare_exchange(pub_ch)
        return pub_ch

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if data.get("type") == "message":
                text = data.get("text", "").strip()
                if not text:
                    continue

                # publish to RabbitMQ (triggers consumer → broadcast)
                try:
                    ch = get_publisher()
                    ch.basic_publish(
                        exchange    = EXCHANGE,
                        routing_key = f"room.{room}",
                        body        = f"{username}: {text}".encode("utf-8"),
                    )
                except Exception as e:
                    print(f"[rabbitmq] publish error: {e}")
                    pub_conn = None  # force reconnect next time

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[ws] error: {e}")
    finally:
        manager.remove(room, ws)
        if pub_conn and pub_conn.is_open:
            try:
                pub_conn.close()
            except Exception:
                pass


# ── Static file serving ───────────────────────────────────────────────────────

@app.get("/")
async def serve_index():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(str(index))


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
