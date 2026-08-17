"""
Adzuna job search API client (France endpoint).

Setup required before this works:
1. Register a free account at https://developer.adzuna.com
2. Create an app to get an app_id and app_key
3. Put them in your .env file (see .env.example)

Docs: https://developer.adzuna.com/docs/search
"""

import os

import requests

SEARCH_URL = "https://api.adzuna.com/v1/api/jobs/fr/search/1"


def search_jobs(keywords: str, where: str = "Paris", max_results: int = 25) -> list[dict]:
    """
    Search job listings on Adzuna's France endpoint.

    keywords    -- free text search, e.g. "marketing communication"
    where       -- location filter, e.g. "Paris"
    max_results -- number of listings to fetch (maps to results_per_page)
    """
    app_id = os.environ["ADZUNA_APP_ID"]
    app_key = os.environ["ADZUNA_APP_KEY"]

    resp = requests.get(
        SEARCH_URL,
        params={
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": max_results,
            "what": keywords,
            "where": where,
            "content-type": "application/json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def normalize_listing(raw: dict) -> dict:
    """Pull out just the fields we need from Adzuna's schema."""
    return {
        "id": str(raw.get("id", "")),
        "source": "adzuna",
        "title": raw.get("title", ""),
        "company": raw.get("company", {}).get("display_name", "Unknown"),
        "location": raw.get("location", {}).get("display_name", ""),
        "description": raw.get("description", ""),
        "contract_type": raw.get("contract_type") or raw.get("contract_time") or "",
        "url": raw.get("redirect_url", ""),
        "date_posted": raw.get("created", ""),
    }


if __name__ == "__main__":
    # Quick manual test: python adzuna.py
    results = search_jobs("marketing communication")
    print(f"Found {len(results)} listings\n")
    for r in results[:5]:
        listing = normalize_listing(r)
        print(f"- {listing['title']} @ {listing['company']} ({listing['location']})")
