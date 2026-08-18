"""
SQLite store of previously-seen listings, so daily runs skip postings
you've already had scored (saves Claude API calls) and never show you
the same listing twice. Also tracks application status per listing, so
the dashboard (api.py) can show what's been applied to and how the
pipeline is progressing.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "jobs.db"

STATUSES = ("new", "applied", "interviewing", "rejected", "skipped")

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT,
    company TEXT,
    location TEXT,
    description TEXT,
    contract_type TEXT,
    url TEXT,
    date_posted TEXT,
    score INTEGER,
    reason TEXT,
    first_seen_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    status_updated_at TEXT,
    PRIMARY KEY (source, external_id)
);
"""

_COLUMNS = (
    "source", "external_id", "title", "company", "location", "description",
    "contract_type", "url", "date_posted", "score", "reason", "first_seen_at",
    "status", "status_updated_at",
)


def _row_to_dict(row: tuple) -> dict:
    job = dict(zip(_COLUMNS, row))
    job["id"] = job.pop("external_id")
    return job


@contextmanager
def connect(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    # Migrate databases created before status tracking / description storage was added.
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(seen_jobs)")}
    if "status" not in existing_cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'new'")
    if "status_updated_at" not in existing_cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN status_updated_at TEXT")
    if "description" not in existing_cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN description TEXT")
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
               (source, external_id, title, company, location, description,
                contract_type, url, date_posted, score, reason, first_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    j["source"], j["id"], j["title"], j["company"], j["location"],
                    j.get("description", ""), j["contract_type"], j["url"],
                    j["date_posted"], j["score"], j["reason"], now,
                )
                for j in scored_listings
            ],
        )


def get_all_jobs(db_path: Path = DB_PATH) -> list[dict]:
    """All scored jobs ever seen, highest score first."""
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM seen_jobs ORDER BY score DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_job(source: str, external_id: str, db_path: Path = DB_PATH) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM seen_jobs WHERE source = ? AND external_id = ?",
            (source, external_id),
        ).fetchone()
    return _row_to_dict(row) if row else None


def update_status(source: str, external_id: str, status: str, db_path: Path = DB_PATH) -> None:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}, got {status!r}")
    now = datetime.now(timezone.utc).isoformat()
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE seen_jobs SET status = ?, status_updated_at = ? WHERE source = ? AND external_id = ?",
            (status, now, source, external_id),
        )


def get_progress_stats(db_path: Path = DB_PATH) -> dict:
    """Counts for the dashboard's progress panel."""
    with connect(db_path) as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM seen_jobs GROUP BY status").fetchall()
    by_status = {s: 0 for s in STATUSES}
    for status, count in rows:
        by_status[status] = count
    return {
        "total_scored": sum(by_status.values()),
        "by_status": by_status,
    }
