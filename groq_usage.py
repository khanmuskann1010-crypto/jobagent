"""
Lightweight local tracker for how many Groq tokens this app has used
today. Groq's rate-limit response headers only cover the per-minute
window (confirmed via their docs) - there's no API to query the daily
quota directly. Two sources of truth are combined instead: every
successful call adds its real response.usage.total_tokens, and every 429
daily-rate-limit error's own message (which does report the org's exact
"Used"/"Limit" values) resyncs the counter, so drift self-corrects.

This is usage tracked BY THIS APP, not Groq's own authoritative
organization total - if the same API key is ever used from somewhere
else, this undercounts. Good enough for "am I close to today's limit,"
not meant as a billing record (see console.groq.com/settings/billing for
that).
"""

import json
import re
from datetime import date
from pathlib import Path

USAGE_PATH = Path(__file__).parent / "groq_usage.json"
DEFAULT_DAILY_LIMIT = 200_000  # openai/gpt-oss-120b free tier, last confirmed via a real 429 - Groq may change this

_LIMIT_RE = re.compile(r"Limit (\d+)")
_USED_RE = re.compile(r"Used (\d+)")


def _fresh(daily_limit: int = DEFAULT_DAILY_LIMIT) -> dict:
    return {"date": date.today().isoformat(), "tokens_used": 0, "daily_limit": daily_limit}


def _load() -> dict:
    if not USAGE_PATH.exists():
        return _fresh()
    try:
        data = json.loads(USAGE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return _fresh()
    if data.get("date") != date.today().isoformat():
        # Groq's window is rolling, not necessarily midnight-aligned, but a
        # fresh calendar day is a reasonable point to stop trusting a stale
        # locally-tracked count and start over.
        return _fresh(data.get("daily_limit", DEFAULT_DAILY_LIMIT))
    return data


def _save(data: dict) -> None:
    try:
        USAGE_PATH.write_text(json.dumps(data))
    except OSError:
        pass  # tracking is best-effort - never let it break a real request


def record_usage(response) -> None:
    """Call after a successful Groq call - adds its real token count."""
    tokens = getattr(getattr(response, "usage", None), "total_tokens", None)
    if not tokens:
        return
    data = _load()
    data["tokens_used"] += tokens
    _save(data)


def record_limit_hit(e: Exception) -> None:
    """Call when a Groq call fails - if it's a daily rate-limit error, Groq's
    own message includes the org's exact Used/Limit values, so resync to
    those instead of trusting our own possibly-drifted running total."""
    text = str(e)
    if "tokens per day" not in text and "(TPD)" not in text:
        return
    limit_match = _LIMIT_RE.search(text)
    used_match = _USED_RE.search(text)
    if not (limit_match and used_match):
        return
    data = _load()
    data["tokens_used"] = int(used_match.group(1))
    data["daily_limit"] = int(limit_match.group(1))
    _save(data)


def get_usage() -> dict:
    data = _load()
    limit = data["daily_limit"]
    used = data["tokens_used"]
    return {
        "date": data["date"],
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "pct": round(min(100, used / limit * 100), 1) if limit else 0,
    }
