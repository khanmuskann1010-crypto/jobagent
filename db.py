"""
SQLite store of previously-seen listings, so daily runs skip postings
you've already had scored (saves Claude API calls) and never show you
the same listing twice.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT,
    company TEXT,
    location TEXT,
    contract_type TEXT,
    url TEXT,
    date_posted TEXT,
    score INTEGER,
    reason TEXT,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (source, external_id)
);
"""


@contextmanager
def connect(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def filter_unseen(listings: list[dict], db_path: Path = DB_PATH) -> list[dict]:
    """Drop listings whose (source, id) is already in the database."""
    with connect(db_path) as conn:
        seen = {row[0] for row in conn.execute("SELECT source || ':' || external_id FROM seen_jobs")}
    return [j for j in listings if j.get("id") and f"{j['source']}:{j['id']}" not in seen]


def save_scored(scored_listings: list[dict], db_path: Path = DB_PATH) -> None:
    """Record scored listings as seen so future runs skip them."""
    now = datetime.now(timezone.utc).isoformat()
    with connect(db_path) as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO seen_jobs
               (source, external_id, title, company, location, contract_type,
                url, date_posted, score, reason, first_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    j["source"], j["id"], j["title"], j["company"], j["location"],
                    j["contract_type"], j["url"], j["date_posted"], j["score"],
                    j["reason"], now,
                )
                for j in scored_listings
            ],
        )
