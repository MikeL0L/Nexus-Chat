# Nexus Chat — Real-Time Multi-User Chat

A real-time live chat system built with **Python (FastAPI)** and **Supabase**,
demonstrating core parallel/distributed systems concepts.

---

## Architecture

```
Browser A ──WebSocket──┐
Browser B ──WebSocket──┤── FastAPI (asyncio) ──── Supabase PostgreSQL
Browser C ──WebSocket──┘         │
                          Background Worker
                          (presence cleanup)
```

### Parallel / Distributed Concepts Demonstrated

| Concept | Implementation |
|---|---|
| Concurrent request handling | `asyncio` + FastAPI WebSocket server handles N clients simultaneously |
| Parallel I/O | `asyncio.gather()` fires DB save + broadcast at the same time |
| Client-server communication | Full-duplex WebSocket (not polling) |
| Background workers | `asyncio.create_task()` — presence cleanup runs every 10s independently |
| Shared persistent state | Supabase PostgreSQL — all clients read/write the same DB |
| Data consistency | Upsert for presence, append-only for messages |
| Auto-reconnect | Exponential backoff on the frontend |

---

## Quick Start

### 1. Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) → **New Project**
2. Open **SQL Editor** → paste the contents of `schema.sql` → **Run**
3. Go to **Project Settings → API** and copy:
   - `Project URL` = SUPABASE_URL=https://lgkymrucwvqlsguicxvc.supabase.co
   - `anon public` key = SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxna3ltcnVjd3ZxbHNndWljeHZjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgwNTMwMTYsImV4cCI6MjA5MzYyOTAxNn0.sFa1YW5NOo_lTjPnQWDKHe1QhX6f6_QEJ_r9Dhh0dwE

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in your SUPABASE_URL and SUPABASE_ANON_KEY
```

### 3. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Run the Server

```bash
python main.py
```

Server starts at `http://localhost:8000`

Open two browser tabs to test multi-user real-time messaging.

---

## Project Structure

```
nexus-chat/
├── main.py          # FastAPI app — WebSocket server, ConnectionManager, background worker
├── database.py      # Supabase client — all DB read/write operations
├── schema.sql       # Run once in Supabase SQL Editor to create tables
├── static/
│   └── index.html   # Frontend — WebSocket client, dark terminal UI
├── requirements.txt
├── .env.example
└── README.md
```

---

## Key Code Patterns

### Concurrent broadcast (main.py)
```python
# All connected clients receive the message simultaneously
await asyncio.gather(*[ws.send_json(payload) for uid, ws in targets])
```

### Parallel DB + broadcast on message send (main.py)
```python
# DB write and WebSocket broadcast happen at the same time
await asyncio.gather(
    asyncio.to_thread(db.save_message, msg),   # Supabase INSERT
    manager.broadcast({"event": "message", "message": msg}),
)
```

### Background worker (main.py)
```python
# Runs independently every 10s — cleans stale presence rows
asyncio.create_task(presence_cleanup_worker())
```

---

## WebSocket Events

| Event (client → server) | Payload |
|---|---|
| `join` | `{event, user: {id, name, color}}` |
| `message` | `{event, message: {id, uid, name, color, text, ts}}` |
| `heartbeat` | `{event, user}` — sent every 5s to stay "online" |

| Event (server → client) | Payload |
|---|---|
| `init` | `{event, messages[], users[], online_count}` |
| `message` | `{event, message}` |
| `user_joined` | `{event, user, users[], online_count}` |
| `user_left` | `{event, user_id, users[], online_count}` |
| `presence_update` | `{event, users[], online_count}` |

---

## Supabase Tables

### `messages`
| Column | Type | Notes |
|---|---|---|
| `id` | TEXT (PK) | Client-generated UUID |
| `user_id` | TEXT | Author's session ID |
| `user_name` | TEXT | Display name |
| `user_color` | TEXT | Hex colour |
| `text` | TEXT | Message body |
| `created_at` | TIMESTAMPTZ | Auto-set by Supabase |

### `presence`
| Column | Type | Notes |
|---|---|---|
| `user_id` | TEXT (PK) | Session ID — upserted on heartbeat |
| `user_name` | TEXT | Display name |
| `user_color` | TEXT | Hex colour |
| `last_seen` | TIMESTAMPTZ | Updated every 5s; rows > 30s old are deleted |
