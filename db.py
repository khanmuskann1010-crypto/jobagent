"""
SQLite store of previously-seen listings, so daily runs skip postings
you've already had scored (saves API calls) and never show you the same
listing twice. Also tracks application status per listing (with a history
log for trend charts), interview dates, and salary text where a source
provides it, so the dashboard (api.py) can show pipeline progress,
follow-up nudges, and an interview calendar.
"""

import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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
    salary TEXT,
    interview_at TEXT,
    PRIMARY KEY (source, external_id)
);
CREATE TABLE IF NOT EXISTS status_history (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    status TEXT NOT NULL,
    changed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

_COLUMNS = (
    "source", "external_id", "title", "company", "location", "description",
    "contract_type", "url", "date_posted", "score", "reason", "first_seen_at",
    "status", "status_updated_at", "salary", "interview_at",
)


def _row_to_dict(row: tuple) -> dict:
    job = dict(zip(_COLUMNS, row))
    job["id"] = job.pop("external_id")
    return job


@contextmanager
def connect(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    # Migrate databases created before status tracking / description / salary /
    # interview scheduling was added.
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(seen_jobs)")}
    if "status" not in existing_cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'new'")
    if "status_updated_at" not in existing_cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN status_updated_at TEXT")
    if "description" not in existing_cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN description TEXT")
    if "salary" not in existing_cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN salary TEXT")
    if "interview_at" not in existing_cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN interview_at TEXT")
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
    """Record scored listings as seen so future runs skip them, and log
    their arrival in status_history so the trend chart has a starting point."""
    now = datetime.now(timezone.utc).isoformat()
    with connect(db_path) as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO seen_jobs
               (source, external_id, title, company, location, description,
                contract_type, url, date_posted, score, reason, first_seen_at, salary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    j["source"], j["id"], j["title"], j["company"], j["location"],
                    j.get("description", ""), j["contract_type"], j["url"],
                    j["date_posted"], j["score"], j["reason"], now, j.get("salary", ""),
                )
                for j in scored_listings
            ],
        )
        conn.executemany(
            "INSERT INTO status_history (source, external_id, status, changed_at) VALUES (?, ?, 'new', ?)",
            [(j["source"], j["id"], now) for j in scored_listings],
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
        conn.execute(
            "INSERT INTO status_history (source, external_id, status, changed_at) VALUES (?, ?, ?, ?)",
            (source, external_id, status, now),
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


def get_stale_applications(days: int = 7, db_path: Path = DB_PATH) -> list[dict]:
    """Applications sitting at 'applied' with no status change in `days` -
    a nudge to follow up, oldest first."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT {', '.join(_COLUMNS)} FROM seen_jobs
                WHERE status = 'applied' AND status_updated_at <= ?
                ORDER BY status_updated_at ASC""",
            (cutoff,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def auto_archive_stale_jobs(days: int = 30, max_score: int = 4, db_path: Path = DB_PATH) -> int:
    """Quietly moves low-score listings nobody's acted on to 'skipped' once
    they've sat untouched for `days`, so the queue doesn't fill up with
    stale noise. Returns how many were archived."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    with connect(db_path) as conn:
        targets = conn.execute(
            "SELECT source, external_id FROM seen_jobs WHERE status = 'new' AND score <= ? AND first_seen_at <= ?",
            (max_score, cutoff),
        ).fetchall()
        if not targets:
            return 0
        conn.executemany(
            "UPDATE seen_jobs SET status = 'skipped', status_updated_at = ? WHERE source = ? AND external_id = ?",
            [(now, s, e) for s, e in targets],
        )
        conn.executemany(
            "INSERT INTO status_history (source, external_id, status, changed_at) VALUES (?, ?, 'skipped', ?)",
            [(s, e, now) for s, e in targets],
        )
    return len(targets)


def set_interview_datetime(source: str, external_id: str, when: str | None, db_path: Path = DB_PATH) -> None:
    """`when` is an ISO 8601 datetime string, or None/"" to clear it."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE seen_jobs SET interview_at = ? WHERE source = ? AND external_id = ?",
            (when or None, source, external_id),
        )


def get_upcoming_interviews(db_path: Path = DB_PATH) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT {', '.join(_COLUMNS)} FROM seen_jobs
                WHERE interview_at IS NOT NULL AND interview_at != ''
                ORDER BY interview_at ASC"""
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_meta(key: str, db_path: Path = DB_PATH) -> str | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(key: str, value: str, db_path: Path = DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_status_trend(days: int = 30, db_path: Path = DB_PATH) -> dict:
    """Cumulative count of jobs that had reached each status by each day in
    the window - e.g. "applied" climbs from 0 to however many total
    applications exist by today. Powers the Insights trend chart."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT status, MIN(changed_at) AS first_at
               FROM status_history
               WHERE status IN ('applied', 'interviewing', 'rejected')
               GROUP BY source, external_id, status"""
        ).fetchall()

    first_day_by_status = defaultdict(list)
    for status, first_at in rows:
        first_day_by_status[status].append(first_at[:10])

    today = datetime.now(timezone.utc).date()
    dates = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]

    series = {}
    for status in ("applied", "interviewing", "rejected"):
        sorted_days = sorted(first_day_by_status[status])
        counts = []
        i, cumulative = 0, 0
        for d in dates:
            while i < len(sorted_days) and sorted_days[i] <= d:
                cumulative += 1
                i += 1
            counts.append(cumulative)
        series[status] = counts

    return {"dates": dates, "series": series}
