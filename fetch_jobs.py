"""
France Travail (ex-Pole Emploi) job search API client.

Setup required before this works:
1. Register a free account + application at https://francetravail.io
2. Subscribe your application to the "Offres d'emploi v2" API
3. You'll get a client_id and client_secret - put them in your .env file
   (see .env.example)

Docs: https://francetravail.io/produits-partages/catalogue/offres-emploi
"""

import os
import requests

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"


def get_access_token() -> str:
    """Authenticate with France Travail using OAuth2 client credentials flow."""
    client_id = os.environ["FRANCE_TRAVAIL_CLIENT_ID"]
    client_secret = os.environ["FRANCE_TRAVAIL_CLIENT_SECRET"]

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "api_offresdemploiv2 o2dsoffre",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def search_jobs(keywords: str, commune: str = "75056", max_results: int = 25) -> list[dict]:
    """
    Search job listings.

    keywords   -- free text search, e.g. "marketing communication"
    commune    -- INSEE commune code; 75056 = Paris. Change or drop for a
                  wider search radius (see API docs for department-level codes)
    max_results -- number of listings to fetch (API paginates in blocks)
    """
    token = get_access_token()

    resp = requests.get(
        SEARCH_URL,
        headers={"Authorization": f"Bearer {token}"},
        params={
            "motsCles": keywords,
            "commune": commune,
            "range": f"0-{max_results - 1}",
            "sort": "1",  # sort by date, most recent first
        },
        timeout=15,
    )

    # France Travail returns 206 (partial content) on a normal successful
    # paginated response - only treat other 4xx/5xx as real errors
    if resp.status_code not in (200, 206):
        resp.raise_for_status()

    data = resp.json()
    return data.get("resultats", [])


def normalize_listing(raw: dict) -> dict:
    """Pull out just the fields we need from France Travail's verbose schema."""
    return {
        "id": raw.get("id"),
        "title": raw.get("intitule", ""),
        "company": raw.get("entreprise", {}).get("nom", "Unknown"),
        "location": raw.get("lieuTravail", {}).get("libelle", ""),
        "description": raw.get("description", ""),
        "contract_type": raw.get("typeContratLibelle", ""),
        "url": raw.get("origineOffre", {}).get("urlOrigine", ""),
        "date_posted": raw.get("dateCreation", ""),
    }


if __name__ == "__main__":
    # Quick manual test: python -m src.fetch_jobs
    results = search_jobs("marketing communication")
    print(f"Found {len(results)} listings\n")
    for r in results[:5]:
        listing = normalize_listing(r)
        print(f"- {listing['title']} @ {listing['company']} ({listing['location']})")
