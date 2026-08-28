import requests

import src.fetch_jobs as fetch_jobs
from src.config import Config
from src.fetch_jobs import (
    FetchJobsError,
    get_access_token,
    normalize_listing,
    search_jobs,
)

TEST_CONFIG = Config(
    anthropic_api_key="sk-test",
    france_travail_client_id="id",
    france_travail_client_secret="secret",
    model="claude-sonnet-5",
    request_timeout=5,
    max_retries=3,
)


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def _reset_token_cache():
    fetch_jobs._token_cache["token"] = None
    fetch_jobs._token_cache["expires_at"] = 0.0


def test_normalize_listing_handles_missing_nested_fields():
    result = normalize_listing({"id": "1", "intitule": "Growth Manager"})
    assert result["company"] == "Unknown"
    assert result["location"] == ""
    assert result["url"] == ""


def test_normalize_listing_handles_null_nested_objects():
    # France Travail can return explicit nulls rather than omitting the key
    raw = {"id": "1", "entreprise": None, "lieuTravail": None, "origineOffre": None}
    result = normalize_listing(raw)
    assert result["company"] == "Unknown"
    assert result["location"] == ""
    assert result["url"] == ""


def test_search_jobs_rejects_non_positive_max_results(monkeypatch):
    _reset_token_cache()
    monkeypatch.setattr(fetch_jobs, "get_access_token", lambda config: "token")
    try:
        search_jobs("marketing", TEST_CONFIG, max_results=0)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_get_access_token_raises_on_missing_field(monkeypatch):
    _reset_token_cache()
    monkeypatch.setattr(
        fetch_jobs.requests, "request", lambda *a, **k: _FakeResponse(200, {"no_token_here": True})
    )
    try:
        get_access_token(TEST_CONFIG)
        assert False, "expected FetchJobsError"
    except FetchJobsError:
        pass


def test_get_access_token_caches_between_calls(monkeypatch):
    _reset_token_cache()
    calls = {"count": 0}

    def fake_request(*args, **kwargs):
        calls["count"] += 1
        return _FakeResponse(200, {"access_token": "tok-123", "expires_in": 300})

    monkeypatch.setattr(fetch_jobs.requests, "request", fake_request)

    first = get_access_token(TEST_CONFIG)
    second = get_access_token(TEST_CONFIG)

    assert first == second == "tok-123"
    assert calls["count"] == 1


def test_request_with_retries_recovers_from_connection_error(monkeypatch):
    attempts = {"count": 0}

    def flaky_request(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise requests.ConnectionError("boom")
        return _FakeResponse(200, {"ok": True})

    monkeypatch.setattr(fetch_jobs.requests, "request", flaky_request)
    monkeypatch.setattr(fetch_jobs.time, "sleep", lambda _: None)

    resp = fetch_jobs._request_with_retries("GET", "https://example.test", TEST_CONFIG)
    assert resp.json() == {"ok": True}
    assert attempts["count"] == 2


def test_request_with_retries_gives_up_after_max_retries(monkeypatch):
    def always_fails(*args, **kwargs):
        raise requests.ConnectionError("still down")

    monkeypatch.setattr(fetch_jobs.requests, "request", always_fails)
    monkeypatch.setattr(fetch_jobs.time, "sleep", lambda _: None)

    try:
        fetch_jobs._request_with_retries("GET", "https://example.test", TEST_CONFIG)
        assert False, "expected FetchJobsError"
    except FetchJobsError:
        pass
