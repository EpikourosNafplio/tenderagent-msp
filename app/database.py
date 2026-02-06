"""SQLite cache for TenderNed data with 30-minute refresh."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "cache.db"
CACHE_TTL_SECONDS = 30 * 60  # 30 minutes


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tenders (
            publicatie_id TEXT PRIMARY KEY,
            data JSON NOT NULL,
            fetched_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cache_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_fetched_at ON tenders(fetched_at);
    """)
    conn.close()


def is_cache_fresh() -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM cache_meta WHERE key = 'last_refresh'"
    ).fetchone()
    conn.close()
    if not row:
        return False
    return (time.time() - float(row["value"])) < CACHE_TTL_SECONDS


def upsert_tenders(tenders: list[dict]) -> int:
    conn = get_connection()
    now = time.time()
    count = 0
    for t in tenders:
        pub_id = str(t.get("publicatieId", ""))
        if not pub_id:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO tenders (publicatie_id, data, fetched_at) VALUES (?, ?, ?)",
            (pub_id, json.dumps(t, ensure_ascii=False), now),
        )
        count += 1
    conn.execute(
        "INSERT OR REPLACE INTO cache_meta (key, value) VALUES ('last_refresh', ?)",
        (str(now),),
    )
    conn.commit()
    conn.close()
    return count


def get_all_tenders() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT data FROM tenders ORDER BY fetched_at DESC").fetchall()
    conn.close()
    return [json.loads(row["data"]) for row in rows]


def get_tender_by_id(pub_id: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT data FROM tenders WHERE publicatie_id = ?", (pub_id,)
    ).fetchone()
    conn.close()
    return json.loads(row["data"]) if row else None


def get_cache_stats() -> dict:
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) as c FROM tenders").fetchone()["c"]
    meta = conn.execute(
        "SELECT value FROM cache_meta WHERE key = 'last_refresh'"
    ).fetchone()
    conn.close()
    last_refresh = float(meta["value"]) if meta else None
    return {
        "cached_tenders": count,
        "last_refresh_epoch": last_refresh,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "cache_fresh": is_cache_fresh(),
    }
