"""
Step 1: research the prospect company.

Scope: fetch and lightly parse their public website (homepage + an
About/Team page if we can find one). No LinkedIn/Crunchbase scraping —
that would need separate, ToS-compliant integrations and is out of scope
for this tool.

Fails soft: if fetching/parsing breaks for any reason, we still return the
user notes so the pipeline doesn't hard-stop on a bad or slow URL.
"""

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ProposalResearchBot/0.1)"}
ABOUT_PATTERNS = re.compile(r"(about|team|company|who-we-are)", re.I)

REQUEST_TIMEOUT = 10
MAX_RESPONSE_BYTES = 5_000_000  # 5MB cap so a huge/malicious page can't hang or exhaust memory
ALLOWED_SCHEMES = {"http", "https"}


def _validate_url(url: str) -> str | None:
    """Return an error message if the URL is unusable, else None."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        return f"Unsupported URL scheme '{parsed.scheme or '(none)'}' — must be http or https"
    if not parsed.netloc:
        return "URL is missing a host"
    return None


def _clean_text(soup: BeautifulSoup, limit: int = 4000) -> str:
    for tag in soup(["script", "style", "nav", "footer", "svg", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    return text[:limit]


def _find_about_link(soup: BeautifulSoup, base_url: str) -> str | None:
    for a in soup.find_all("a", href=True):
        label = f"{a.get_text()} {a['href']}"
        if ABOUT_PATTERNS.search(label):
            candidate = urljoin(base_url, a["href"])
            if urlparse(candidate).scheme in ALLOWED_SCHEMES:
                return candidate
    return None


def _fetch(url: str) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, stream=True)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "html" not in content_type.lower():
        raise ValueError(f"Expected HTML, got Content-Type '{content_type}'")

    # Read up to the size cap rather than trusting Content-Length (which can lie/be absent)
    chunks = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise ValueError(f"Response exceeded {MAX_RESPONSE_BYTES} byte cap")
        chunks.append(chunk)
    resp._content = b"".join(chunks)
    return resp


def research_company(name: str, url: str, user_notes: str = "") -> dict:
    """
    Returns a plain dict with whatever context we could gather.
    Fails soft: if scraping breaks, we still return the user notes so
    the pipeline doesn't hard-stop on a bad URL.
    """
    result = {
        "name": name,
        "url": url,
        "user_notes": user_notes,
        "homepage_text": "",
        "about_text": "",
        "domain": urlparse(url).netloc if url else "",
        "fetch_error": None,
    }

    if not url:
        return result

    url_error = _validate_url(url)
    if url_error:
        result["fetch_error"] = url_error
        return result

    try:
        resp = _fetch(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        result["homepage_text"] = _clean_text(soup)

        about_url = _find_about_link(soup, url)
        if about_url and about_url != url:
            try:
                about_resp = _fetch(about_url)
                about_soup = BeautifulSoup(about_resp.text, "html.parser")
                result["about_text"] = _clean_text(about_soup, limit=2500)
            except (requests.RequestException, ValueError):
                # About page is a bonus, not required — homepage data is enough to proceed
                pass

    except requests.Timeout:
        result["fetch_error"] = f"Timed out after {REQUEST_TIMEOUT}s fetching {url}"
    except requests.RequestException as e:
        result["fetch_error"] = str(e)
    except ValueError as e:
        result["fetch_error"] = str(e)

    return result


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m src.research <company_name> <url> [notes]")
        sys.exit(1)

    company_name, company_url = sys.argv[1], sys.argv[2]
    notes = sys.argv[3] if len(sys.argv) > 3 else ""
    print(json.dumps(research_company(company_name, company_url, notes), indent=2))
