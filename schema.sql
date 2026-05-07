-- =====================================================
-- Nexus Chat — Supabase Schema
-- Run this entire file in the Supabase SQL Editor
-- (Dashboard → SQL Editor → New Query → Paste → Run)
-- =====================================================


-- ── Messages ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id          TEXT        PRIMARY KEY,
    user_id     TEXT        NOT NULL,
    user_name   TEXT        NOT NULL,
    user_color  TEXT        NOT NULL,
    text        TEXT        NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast ordered fetches
CREATE INDEX IF NOT EXISTS messages_created_at_idx ON messages (created_at ASC);


-- ── Presence ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS presence (
    user_id     TEXT        PRIMARY KEY,
    user_name   TEXT        NOT NULL,
    user_color  TEXT        NOT NULL,
    last_seen   TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast "recently active" queries
CREATE INDEX IF NOT EXISTS presence_last_seen_idx ON presence (last_seen DESC);


-- ── Row Level Security ────────────────────────────
-- Disabled for this demo so the anon key has full access.
-- In production: enable RLS and add proper policies.

ALTER TABLE messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE presence DISABLE ROW LEVEL SECURITY;


-- ── Optional: Realtime ────────────────────────────
-- If you want Supabase Realtime on top of WebSockets,
-- enable it per table in the Supabase dashboard:
--   Database → Replication → Tables → toggle messages & presence

-- =====================================================
-- Verify tables were created
-- =====================================================
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('messages', 'presence');
