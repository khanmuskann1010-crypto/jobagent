"""
Indeed listings, sourced via Claude's Indeed connector
(mcp__Indeed__search_jobs / mcp__Indeed__get_job_details) rather than a
public REST API - Indeed has no open developer API a standalone script
can call directly, so fetching only works from inside a live Claude
session that has this connector attached.

This module just parses the *text* those two tools return into the same
schema fetch_jobs.py/adzuna.py use, so results can be merged into the
regular dedupe -> score -> digest pipeline via `main.py --extra-listings`.
The actual tool calls happen in the Claude session driving a run (see the
daily Routine prompt), not in this file.
"""

import re

_SEARCH_BLOCK_RE = re.compile(
    r"\*\*Job Title:\*\*\s*(?P<title>.+?)\s*\n"
    r"\s*\*\*Job Id:\*\*\s*(?P<id>.+?)\s*\n"
    r"\s*\*\*Company:\*\*\s*(?P<company>.+?)\s*\n"
    r"\s*\*\*Location:\*\*\s*(?P<location>.+?)\s*\n"
    r"\s*\*\*Posted on:\*\*\s*(?P<posted>.+?)\s*\n"
    r"\s*\*\*Job Type:\*\*\s*(?P<job_type>.+?)\s*\n"
    r"\s*\*\*Compensation:\*\*\s*(?P<comp>.+?)\s*\n"
    r"\s*\*\*View Job URL:\*\*\s*(?P<url>\S+)"
)

_DETAILS_RE = re.compile(
    r"###\s*(?P<title>.+?)\s*\n"
    r"\s*\*\*View Job URL:\*\*\s*(?P<url>\S+)\s*\n"
    r"\s*\*\*Job Id:\*\*\s*(?P<id>.+?)\s*\n"
    r"\s*\*\*Company:\*\*\s*(?P<company>.+?)\s*\n"
    r"\s*\*\*Location:\*\*\s*(?P<location>.+?)\s*\n"
    r"\s*\*\*Posted on:\*\*\s*(?P<posted>.+?)\s*\n"
    r"\s*\*\*Job Type:\*\*\s*(?P<job_type>.+?)\s*\n"
    r"\s*\*\*Compensation:\*\*\s*(?P<comp>.+?)\s*\n\n"
    r"(?P<description>.+)",
    re.DOTALL,
)


def parse_search_results(raw_text: str) -> list[dict]:
    """Parse mcp__Indeed__search_jobs's text into listing dicts (no description yet)."""
    listings = []
    for m in _SEARCH_BLOCK_RE.finditer(raw_text):
        listings.append(
            {
                "id": m.group("id").strip(),
                "source": "indeed",
                "title": m.group("title").strip(),
                "company": m.group("company").strip(),
                "location": m.group("location").strip(),
                "description": "",
                "contract_type": m.group("job_type").strip(),
                "url": m.group("url").strip(),
                "date_posted": m.group("posted").strip(),
            }
        )
    return listings


def parse_job_details(raw_text: str) -> str:
    """Parse mcp__Indeed__get_job_details's text, return just the description body."""
    m = _DETAILS_RE.search(raw_text)
    return m.group("description").strip() if m else ""
