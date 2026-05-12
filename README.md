# Nexus Chat — Real-Time Multi-User Chat
## By Cassion Group - (Cassion, Soriano, Camariosa, Pabellan, Cabot) - CS3C

A real-time live chat system built with **Python (FastAPI)** and **Supabase**, demonstrating core parallel/distributed systems concepts.

---

## Overview

This project is a FastAPI WebSocket chat server that uses Supabase as a shared PostgreSQL backend. It supports:

- real-time WebSocket messaging
- online presence tracking
- background cleanup for stale presence rows
- local development and Render deployment

---

## Architecture

```
Browser A ──WebSocket──┐
Browser B ──WebSocket──┤── FastAPI (asyncio) ──── Supabase PostgreSQL
Browser C ──WebSocket──┘         │
                         Background Worker
                         (presence cleanup)
```

### Concepts Demonstrated

| Concept | Implementation |
|---|---|
| Concurrent request handling | `asyncio` + FastAPI WebSocket server handles multiple clients simultaneously |
| Parallel I/O | `asyncio.gather()` fires DB save + broadcast at the same time |
| Client-server communication | Full-duplex WebSocket (not polling) |
| Background workers | `asyncio.create_task()` — presence cleanup runs every 10s independently |
| Shared persistent state | Supabase PostgreSQL — all clients read/write the same DB |
| Data consistency | Upsert for presence, append-only for messages |
| Deployment-ready | `PORT` support for Render / hosted servers |

---

## Local Setup

### 1. Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) → **New Project**
2. Open **SQL Editor** → paste the contents of `schema.sql` → **Run**
3. Go to **Project Settings → API** and copy:
   - `Project URL`
   - `anon public` key

### 2. Configure Environment

Create a local `.env` file in the root folder with:

```ini
SUPABASE_URL=<your-supabase-url>
SUPABASE_ANON_KEY=<your-supabase-anon-key>
```

> `.env` is excluded from Git and should not be committed.

### 3. Install Dependencies

```bash
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

### 4. Run Locally

```bash
python main.py
```

Or with Uvicorn directly:

```bash
uvicorn main:app --reload
```

The app starts on `http://localhost:8000` by default.

---

## Render Deployment

This app is ready for Render deployment.

### Build Command

```bash
pip install -r requirements.txt
```

### Start Command

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Environment Variables

Set these in Render:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`

The `main.py` entrypoint supports `PORT` and defaults to `8000` if not set.

---

## Project Structure

```
./
├── main.py          # FastAPI app — WebSocket server, ConnectionManager, background worker
├── database.py      # Supabase client — all DB read/write operations
├── requirements.txt
├── schema.sql       # Use in Supabase SQL Editor to create tables
├── static/
│   └── index.html   # Frontend WebSocket client UI
├── README.md
└── .gitignore
```

---

## Key Code Patterns

### Concurrent broadcast (main.py)
```python
await asyncio.gather(*[_safe_send(uid, ws) for uid, ws in targets])
```

### Parallel DB + broadcast on message send (main.py)
```python
await asyncio.gather(
    asyncio.to_thread(db.save_message, msg),
    manager.broadcast({"event": "message", "message": msg}),
)
```

### Background worker (main.py)
```python
asyncio.create_task(presence_cleanup_worker())
```

---

## WebSocket Events

| Event (client → server) | Payload |
|---|---|
| `join` | `{event, user: {id, name, color}}` |
| `message` | `{event, message: {id, uid, name, color, text, ts}}` |
| `heartbeat` | `{event, user}` — sent every 5s to stay online |

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
