"""
Checks whether a job listing's URL still resolves to a live posting, so the
dashboard can flag ones that have been pulled from the platform instead of
sending you to apply to something that's already gone.

Deliberately conservative: job boards routinely 403/429 non-browser
requests even for postings that are still live, so anything other than a
clear "not found" is treated as 'unknown' rather than 'dead'. False
positives (flagging a live job as dead) are worse than a few missed dead
ones, since they'd make you second-guess real opportunities.
"""

import requests

import db

TIMEOUT = 8
DEAD_STATUS_CODES = {404, 410}
USER_AGENT = "Mozilla/5.0 (compatible; JobAgentLinkCheck/1.0)"


def check_url(url: str) -> str:
    """Returns 'live', 'dead', or 'unknown'."""
    if not url:
        return "unknown"
    try:
        resp = requests.head(url, timeout=TIMEOUT, allow_redirects=True, headers={"User-Agent": USER_AGENT})
        if resp.status_code == 405:  # some sites reject HEAD outright
            resp = requests.get(url, timeout=TIMEOUT, allow_redirects=True, headers={"User-Agent": USER_AGENT})
        if resp.status_code in DEAD_STATUS_CODES:
            return "dead"
        if 200 <= resp.status_code < 400:
            return "live"
        return "unknown"
    except requests.RequestException:
        return "unknown"


def check_listings(jobs: list[dict]) -> int:
    """Checks each job's URL and writes the result via db.set_link_status.
    jobs are dicts with "source", "id", "url" (db.get_jobs_to_recheck's
    shape). Returns how many came back 'dead'."""
    dead_count = 0
    for job in jobs:
        status = check_url(job.get("url", ""))
        db.set_link_status(job["source"], job["id"], status)
        if status == "dead":
            dead_count += 1
    return dead_count
