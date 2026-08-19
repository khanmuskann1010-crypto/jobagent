"""
Welcome to the Jungle job search client.

WTTJ has no official public developer API. This calls the same public,
search-only Algolia index their own website's search box queries directly -
no signup or key of your own needed, since it's the same read-only key
already embedded in welcometothejungle.com's front-end. Because it's
unofficial, it could stop working if WTTJ ever rotates that key; if
search_jobs() starts erroring, that's the first thing to check.

Run `python wttj.py` to sanity-check the connection and print a couple of
raw hits - normalize_listing() below is provisional until confirmed
against real response data.
"""

import requests

ALGOLIA_URL = "https://csekhvms53-dsn.algolia.net/1/indexes/*/queries"
APP_ID = "CSEKHVMS53"
API_KEY = "4bd8f6215d0cc52b26430765769e65a0"
JOB_INDEX = "wk_cms_jobs_production"


def search_jobs(keywords: str, max_results: int = 25) -> list[dict]:
    """
    Search job listings on Welcome to the Jungle via their public Algolia index.

    keywords    -- free text search, e.g. "growth marketing"
    max_results -- number of listings to fetch (maps to hitsPerPage)
    """
    resp = requests.post(
        ALGOLIA_URL,
        headers={
            "x-algolia-application-id": APP_ID,
            "x-algolia-api-key": API_KEY,
            "content-type": "application/json",
        },
        json={
            "requests": [
                {
                    "indexName": JOB_INDEX,
                    "params": f"query={keywords}&hitsPerPage={max_results}",
                }
            ]
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["results"][0].get("hits", [])


def normalize_listing(raw: dict) -> dict:
    """Pull out the fields we need from a WTTJ Algolia hit.

    PROVISIONAL - field names are a best guess based on how similar Algolia-
    backed job indexes are typically shaped (WTTJ's own site isn't reachable
    to verify from this environment). Run `python wttj.py` against a real
    response and adjust the .get() keys below to match what's actually there.
    """
    org = raw.get("organization", {}) or {}
    offices = raw.get("offices", []) or []
    location = ", ".join(filter(None, [o.get("city") for o in offices])) or ""
    return {
        "id": str(raw.get("objectID") or raw.get("reference") or ""),
        "source": "wttj",
        "title": raw.get("name", ""),
        "company": org.get("name", "Unknown"),
        "location": location,
        "description": raw.get("description", ""),
        "contract_type": raw.get("contract_type", ""),
        "url": (
            f"https://www.welcometothejungle.com/en/companies/{org.get('slug')}/jobs/{raw.get('slug')}"
            if org.get("slug") and raw.get("slug") else ""
        ),
        "date_posted": raw.get("published_at", ""),
        "salary": "",
    }


if __name__ == "__main__":
    # Quick manual test: python wttj.py
    results = search_jobs("growth marketing")
    print(f"Found {len(results)} listings\n")
    import json
    for r in results[:3]:
        print(json.dumps(r, indent=2, ensure_ascii=False))
        print("---")
