"""
France Travail (ex-Pole Emploi) job search API client.

Setup required before this works:
1. Register a free account + application at https://francetravail.io
2. Subscribe your application to the "Offres d'emploi v2" API
3. You'll get a client_id and client_secret - put them in your .env file
   (see .env.example)

Docs: https://francetravail.io/produits-partages/catalogue/offres-emploi
"""

import time

import requests

from src.config import Config

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

# Simple in-memory cache so a run that calls search_jobs more than once
# doesn't re-authenticate every time; not persisted across processes.
_token_cache: dict = {"token": None, "expires_at": 0.0}


class FetchJobsError(Exception):
    """Raised when the France Travail API can't be reached or returns something unusable."""


def _request_with_retries(method: str, url: str, config: Config, **kwargs) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, config.max_retries + 1):
        try:
            resp = requests.request(method, url, timeout=config.request_timeout, **kwargs)
            # 206 is a normal successful paginated response from this API; only
            # treat other 4xx/5xx as errors worth raising/retrying on.
            if resp.status_code in (200, 206):
                return resp
            if resp.status_code >= 500 and attempt < config.max_retries:
                last_error = FetchJobsError(f"{url} returned {resp.status_code}")
                time.sleep(min(2**attempt, 10))
                continue
            resp.raise_for_status()
            return resp
        except requests.Timeout as e:
            last_error = e
            if attempt < config.max_retries:
                time.sleep(min(2**attempt, 10))
                continue
        except requests.ConnectionError as e:
            last_error = e
            if attempt < config.max_retries:
                time.sleep(min(2**attempt, 10))
                continue

    raise FetchJobsError(f"Failed to reach {url} after {config.max_retries} attempts: {last_error}")


def get_access_token(config: Config) -> str:
    """Authenticate with France Travail using OAuth2 client credentials flow, caching the token."""
    now = time.monotonic()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    resp = _request_with_retries(
        "POST",
        TOKEN_URL,
        config,
        data={
            "grant_type": "client_credentials",
            "client_id": config.france_travail_client_id,
            "client_secret": config.france_travail_client_secret,
            "scope": "api_offresdemploiv2 o2dsoffre",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        payload = resp.json()
        token = payload["access_token"]
    except (ValueError, KeyError) as e:
        raise FetchJobsError(
            "France Travail token response didn't include an access_token — check your "
            "FRANCE_TRAVAIL_CLIENT_ID/SECRET and that your app is subscribed to 'Offres d'emploi v2'."
        ) from e

    # Refresh a little early to avoid racing an expiry mid-request
    expires_in = payload.get("expires_in", 300)
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + max(expires_in - 30, 0)
    return token


def search_jobs(keywords: str, config: Config, commune: str = "75056", max_results: int = 25) -> list[dict]:
    """
    Search job listings.

    keywords    -- free text search, e.g. "marketing communication"
    commune     -- INSEE commune code; 75056 = Paris. Change or drop for a
                   wider search radius (see API docs for department-level codes)
    max_results -- number of listings to fetch (API paginates in blocks)
    """
    if max_results < 1:
        raise ValueError("max_results must be at least 1")

    token = get_access_token(config)

    resp = _request_with_retries(
        "GET",
        SEARCH_URL,
        config,
        headers={"Authorization": f"Bearer {token}"},
        params={
            "motsCles": keywords,
            "commune": commune,
            "range": f"0-{max_results - 1}",
            "sort": "1",  # sort by date, most recent first
        },
    )

    try:
        data = resp.json()
    except ValueError as e:
        raise FetchJobsError("France Travail search response wasn't valid JSON") from e

    return data.get("resultats", [])


def normalize_listing(raw: dict) -> dict:
    """Pull out just the fields we need from France Travail's verbose schema."""
    return {
        "id": raw.get("id"),
        "title": raw.get("intitule", ""),
        "company": (raw.get("entreprise") or {}).get("nom") or "Unknown",
        "location": (raw.get("lieuTravail") or {}).get("libelle", ""),
        "description": raw.get("description", ""),
        "contract_type": raw.get("typeContratLibelle", ""),
        "url": (raw.get("origineOffre") or {}).get("urlOrigine", ""),
        "date_posted": raw.get("dateCreation", ""),
    }


if __name__ == "__main__":
    # Quick manual test: python -m src.fetch_jobs
    from src.config import load_config

    cfg = load_config()
    results = search_jobs("marketing communication", cfg)
    print(f"Found {len(results)} listings\n")
    for r in results[:5]:
        listing = normalize_listing(r)
        print(f"- {listing['title']} @ {listing['company']} ({listing['location']})")
