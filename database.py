"""
database.py — Supabase client and all DB operations

Tables used:
  - messages   : persistent chat history
  - presence   : online user tracking (TTL-based)
"""

import os
import uuid
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ──────────────────────────────────────────────
# Client (singleton)
# ──────────────────────────────────────────────

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_ANON_KEY", "")
        if not url or not key:
            raise EnvironmentError(
                "SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env"
            )
        _client = create_client(url, key)
    return _client


# ──────────────────────────────────────────────
# Messages
# ──────────────────────────────────────────────

def get_messages(limit: int = 100) -> list[dict]:
    """Fetch the latest N messages ordered by creation time."""
    client = get_client()
    result = (
        client.table("messages")
        .select("id, user_id, user_name, user_color, text, created_at")
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    # Normalise to the shape the frontend expects
    return [
        {
            "id":        row["id"],
            "uid":       row["user_id"],
            "name":      row["user_name"],
            "color":     row["user_color"],
            "text":      row["text"],
            "ts":        _to_ms(row["created_at"]),
        }
        for row in (result.data or [])
    ]


def save_message(msg: dict) -> dict:
    """
    Persist a single message.
    msg keys: id, uid, name, color, text, ts
    """
    client = get_client()
    result = (
        client.table("messages")
        .insert({
            "id":         msg.get("id", str(uuid.uuid4())),
            "user_id":    msg["uid"],
            "user_name":  msg["name"],
            "user_color": msg["color"],
            "text":       msg["text"],
        })
        .execute()
    )
    return result.data[0] if result.data else {}


# ──────────────────────────────────────────────
# Presence
# ──────────────────────────────────────────────

PRESENCE_TTL_SECONDS = 15   # users gone > 15s are considered offline
STALE_TTL_SECONDS    = 30   # rows older than 30s are deleted by the worker


def upsert_presence(user: dict) -> None:
    """Insert or update a user's last_seen timestamp."""
    client = get_client()
    client.table("presence").upsert(
        {
            "user_id":    user["id"],
            "user_name":  user["name"],
            "user_color": user["color"],
            "last_seen":  _now_iso(),
        },
        on_conflict="user_id",
    ).execute()


def remove_presence(user_id: str) -> None:
    """Immediately delete a user's presence row on disconnect."""
    client = get_client()
    client.table("presence").delete().eq("user_id", user_id).execute()


def get_online_users(ttl: int = PRESENCE_TTL_SECONDS) -> list[dict]:
    """Return all users seen within the last `ttl` seconds."""
    client = get_client()
    cutoff = _ago_iso(ttl)
    result = (
        client.table("presence")
        .select("user_id, user_name, user_color, last_seen")
        .gte("last_seen", cutoff)
        .execute()
    )
    return [
        {
            "id":       row["user_id"],
            "name":     row["user_name"],
            "color":    row["user_color"],
            "last_seen": row["last_seen"],
        }
        for row in (result.data or [])
    ]


def cleanup_stale_presence(ttl: int = STALE_TTL_SECONDS) -> int:
    """
    Delete presence rows older than `ttl` seconds.
    Called by the background worker every 10s.
    Returns the number of rows removed.
    """
    client = get_client()
    cutoff = _ago_iso(ttl)
    result = client.table("presence").delete().lt("last_seen", cutoff).execute()
    return len(result.data or [])


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ago_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _to_ms(iso_str: str) -> int:
    """Convert Supabase ISO timestamp → Unix milliseconds for the frontend."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0
